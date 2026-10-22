"""Автоматическая проверка вопросов бенчмарка: `python -m benchmarks.check_questions [--llm]`.

Без `--llm` выполняются бесплатные проверки:
- числа из эталонного ответа ищутся в эталонных фрагментах (с учётом масштаба
  тыс./млн/млрд и процентов). Не найденное число означает вычисленный ответ или ошибку;
- эталонные фрагменты ищутся в других документах того же домена. Совпадение означает,
  что вопрос может быть неоднозначным.

С `--llm` модель `check` (LiteLLM, другое семейство, чем генератор, судья и автор черновика)
делает три вызова на вопрос:
1. `review`: видит вопрос, эталон, фрагменты и окно документа и оценивает, следует ли
   ответ из фрагментов, хватает ли их, нет ли в документе противоречия, понятен ли вопрос;
2. `solve`: отвечает на вопрос по окну документа, не видя эталона;
3. `compare`: сравнивает свой ответ с эталонным.

Ответы модели кешируются в `benchmarks/results/checks/<модель>.jsonl` (ключ — id вопроса,
вид вызова и хеш промпта), повторный запуск не тратит бюджет. Отчёт пишется
в `benchmarks/datasets/check_report.md`.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import re
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI, RateLimitError

from app.config import get_settings
from app.ingest.parsers import parse_bytes
from benchmarks.dataset import (
    CORPUS_DIR,
    DATASETS_DIR,
    DOMAINS,
    ROOT,
    Sample,
    evidence_in,
    normalize,
    read_samples,
)

logger = logging.getLogger('benchmarks.check')

CHECKS_DIR = ROOT / 'results' / 'checks'
REPORT_PATH = DATASETS_DIR / 'check_report.md'
CHECK_MODEL = 'check'

# Окно документа вокруг первого эталонного фрагмента (символов в каждую сторону).
WINDOW_CHARS = 3000
MAX_CONCURRENCY = 4
# OpenRouter ограничивает новые аккаунты 20 запросами в минуту на модель.
REQUESTS_PER_MINUTE = 18
RATE_LIMIT_RETRIES = 5
RATE_LIMIT_BACKOFF_S = 30.0
MAX_TOKENS = 800
# Цены модели проверки, $ за 1M токенов (OpenRouter, openai/gpt-5.6-luna, 2026-10-23):
# нужны только для оценки стоимости в отчёте.
PRICE_IN, PRICE_OUT = 0.20, 1.20

_NUMBER = re.compile(r'(?<![\w.])-?\d+(?:[.,]\d+)?')
# Номера статей, пунктов и частей — не данные, их в эталонных фрагментах нет.
# Номера статей, пунктов и частей — не данные, их в эталонных фрагментах нет; учитываются
# и перечисления («ч. 13, 14», «п. 12.5.1, 12.5.4»).
_REFERENCE_PREFIX = re.compile(
    r'(?:ст\.|статьи|статья|п\.|пп\.|ч\.|гл\.|§|section|article)\s*(?:[\d.]+\s*(?:,|и)\s*)*$',
    re.I,
)
# Номер закона: «44-ФЗ».
_LAW_SUFFIX = re.compile(r'^-фз')
# Даты и периоды: «31 декабря», «31.12», «6 месяцев», «4 кв.».
_PERIOD = re.compile(
    r'^(?:\.\d\d\b|\s*(?:январ|феврал|март|апрел|ма[яй]|июн|июл|август|сентябр|октябр|ноябр|декабр'
    r'|месяц|квартал|кв\.))'
)
_YEAR = re.compile(r'^(19|20)\d\d$')


# --- проверки без LLM ---------------------------------------------------------------------


def _numbers(text: str) -> list[tuple[str, float]]:
    """Числа из текста (после удаления разделителей тысяч), кроме номеров статей и годов."""
    text = normalize(text)
    found = []
    for match in _NUMBER.finditer(text):
        raw = match.group()
        if _REFERENCE_PREFIX.search(text[max(0, match.start() - 40) : match.start()]):
            continue
        if _LAW_SUFFIX.match(text[match.end() :]) or _PERIOD.match(text[match.end() :]):
            continue
        if _YEAR.match(raw):
            continue
        found.append((raw, float(raw.replace(',', '.'))))
    return found


def _decimals(raw: str) -> int:
    return len(re.split(r'[.,]', raw)[1]) if re.search(r'[.,]', raw) else 0


def number_supported(raw: str, value: float, evidence_values: Iterable[float]) -> bool:
    """Есть ли число ответа среди чисел фрагментов с точностью до округления и масштаба.

    Масштабы: тысячи/миллионы/миллиарды (`807186` млн ↔ `807,2` млрд) и проценты
    (`0.323` ↔ `32,3%`). Знак не учитывается: расходы в отчётах отрицательные.

    Args:
        raw: Число из ответа как в тексте.
        value: Его значение.
        evidence_values: Числа из эталонных фрагментов.

    Returns:
        `True`, если число нашлось.
    """
    digits = _decimals(raw)
    tolerance = 0.5 * 10**-digits + 1e-9
    for candidate in evidence_values:
        for scale in (1, 1e-3, 1e-6, 1e-9, 1e3, 100):
            if abs(abs(candidate * scale) - abs(value)) <= tolerance:
                return True
    return False


def unsupported_numbers(sample: Sample) -> list[str]:
    """Числа эталонного ответа, которых нет в эталонных фрагментах.

    Args:
        sample: Вопрос.

    Returns:
        Числа в виде, как они записаны в ответе.
    """
    evidence_text = ' '.join([*sample.reference_contexts, *(s for g in sample.evidence for s in g)])
    evidence_values = [v for _, v in _numbers(evidence_text)]
    checked = sample.ground_truth
    if program := sample.metadata.get('program'):
        # FinQA: ответ вычислен программой, проверяем её аргументы. Константы (`const_100`)
        # и ссылки на промежуточные результаты (`#0`) — не данные документа.
        checked = re.sub(r'const_[\w.]+|#\d+', ' ', program)
    return [
        raw for raw, value in _numbers(checked) if not number_supported(raw, value, evidence_values)
    ]


@dataclass(slots=True)
class Corpus:
    """Тексты документов корпуса: исходный (для окон) и нормализованный (для поиска)."""

    raw: dict[str, str] = field(default_factory=dict)
    normalized: dict[str, str] = field(default_factory=dict)

    def load(self, rel_path: str) -> None:
        """Разбирает документ, если он ещё не загружен."""
        if rel_path in self.raw:
            return
        path = CORPUS_DIR / rel_path
        doc = parse_bytes(path.read_bytes(), path.name, source=rel_path)
        rows = (' | '.join(row) for t in doc.tables for row in [t.header, *t.rows])
        text = re.sub(r'[ \t]+', ' ', '\n'.join([doc.text, *rows]))
        self.raw[rel_path] = text
        self.normalized[rel_path] = normalize(text)

    def domain_docs(self, domain: str) -> list[str]:
        """Пути всех документов домена в корпусе."""
        return sorted(
            str(p.relative_to(CORPUS_DIR))
            for p in (CORPUS_DIR / domain).rglob('*')
            if p.is_file() and not p.name.startswith('.')
        )

    def window(self, rel_path: str, fragment: str, chars: int) -> str:
        """Окно исходного текста вокруг фрагмента; если фрагмент не найден — начало документа."""
        text = self.raw[rel_path]
        probe = re.sub(r'\s+', ' ', fragment).strip()[:60].lower()
        flat = re.sub(r'\s', ' ', text).lower()
        pos = flat.find(probe) if probe else -1
        if pos < 0:
            pos = 0
        start = max(0, pos - chars)
        return text[start : pos + chars]


def evidence_elsewhere(sample: Sample, corpus: Corpus, domain_docs: list[str]) -> list[str]:
    """Документы вне `source_docs`, в которых тоже есть все эталонные фрагменты вопроса.

    Args:
        sample: Вопрос.
        corpus: Загруженные тексты.
        domain_docs: Документы домена.

    Returns:
        Пути документов, где эталон тоже находится (кандидаты на неоднозначность).
    """
    others = []
    for doc in domain_docs:
        if doc in sample.source_docs:
            continue
        corpus.load(doc)
        if sample.evidence and all(evidence_in(g, corpus.normalized[doc]) for g in sample.evidence):
            others.append(doc)
    return others


# --- проверки LLM ------------------------------------------------------------------------

REVIEW_PROMPT = """You audit a question-answering benchmark built from documents.
You receive a QUESTION, a REFERENCE ANSWER, the EVIDENCE fragments it is based on, and a
DOCUMENT EXCERPT around the evidence. Documents and questions may be in Russian or English.

Judge strictly:
- answer_supported: every factual claim of the reference answer follows from the evidence
  (simple arithmetic over evidence numbers is allowed);
- evidence_sufficient: the evidence alone is enough to answer the question;
- document_conflict: the excerpt contains information that contradicts or materially changes
  the reference answer (exceptions, newer values, other periods);
- question_clear: the question is unambiguous for a user who has many documents of this kind
  and does not know which one is meant (company, contract, law and period are identifiable).

Reply with JSON only:
{"answer_supported": true|false, "evidence_sufficient": true|false,
 "document_conflict": true|false, "question_clear": true|false,
 "verdict": "ok"|"suspect"|"wrong", "issues": "<short explanation, empty if ok>"}"""

SOLVE_PROMPT = """Answer the question using only the document excerpts below. Be concise and
precise: copy numbers, dates and identifiers exactly; show the calculation if one is needed.
If the excerpts do not contain the answer, reply exactly: NOT IN DOCUMENT.
Answer in the language of the question."""

COMPARE_PROMPT = """Compare a CANDIDATE answer with the REFERENCE answer to the same question.
They match if the candidate states the same key facts (numbers may differ only by rounding or
units, wording may differ). Extra correct details in the candidate are fine. Reply with JSON
only: {"match": "yes"|"partial"|"no", "difference": "<short, empty if yes>"}"""


@dataclass(slots=True)
class LlmChecker:
    """Вызовы модели проверки с кешем на диске и учётом токенов."""

    client: AsyncOpenAI
    cache_path: Path
    reasoning: bool
    semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(MAX_CONCURRENCY))
    cache: dict[str, dict[str, Any]] = field(default_factory=dict)
    usage: Counter[str] = field(default_factory=Counter)
    _pace: asyncio.Lock = field(default_factory=asyncio.Lock)
    _next_start: float = 0.0

    def __post_init__(self) -> None:
        if self.cache_path.exists():
            for line in self.cache_path.read_text(encoding='utf-8').splitlines():
                record = json.loads(line)
                self.cache[record['key']] = record

    async def call(self, sample_id: str, kind: str, system: str, user: str) -> dict[str, Any]:
        """Вызывает модель (или берёт ответ из кеша) и разбирает JSON-ответ.

        Args:
            sample_id: id вопроса.
            kind: Вид вызова (`review`, `solve`, `compare`).
            system: Системный промпт.
            user: Сообщение пользователя.

        Returns:
            Запись кеша: `content` (текст), `parsed` (JSON или `None`), токены.
        """
        digest = hashlib.sha256(f'{system}\n{user}\n{self.reasoning}'.encode()).hexdigest()[:16]
        key = f'{sample_id}:{kind}:{digest}'
        if key in self.cache:
            return self.cache[key]
        extra: dict[str, Any] = {} if self.reasoning else {'reasoning': {'enabled': False}}
        async with self.semaphore:
            for attempt in range(1, RATE_LIMIT_RETRIES + 1):
                await self._wait_turn()
                try:
                    response = await self.client.chat.completions.create(
                        model=CHECK_MODEL,
                        messages=[
                            {'role': 'system', 'content': system},
                            {'role': 'user', 'content': user},
                        ],
                        temperature=0,
                        max_tokens=MAX_TOKENS * (4 if self.reasoning else 1),
                        extra_body=extra,
                    )
                    break
                except RateLimitError:
                    if attempt == RATE_LIMIT_RETRIES:
                        raise
                    logger.warning(
                        '%s: лимит запросов, повтор через %s с', key, RATE_LIMIT_BACKOFF_S
                    )
                    await asyncio.sleep(RATE_LIMIT_BACKOFF_S)
        content = response.choices[0].message.content or ''
        usage = response.usage
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        record: dict[str, Any] = {
            'key': key,
            'id': sample_id,
            'kind': kind,
            'content': content,
            'parsed': _parse_json(content) if kind != 'solve' else None,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
        }
        self.usage['prompt_tokens'] += prompt_tokens
        self.usage['completion_tokens'] += completion_tokens
        self.usage['calls'] += 1
        self.cache[key] = record
        with self.cache_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        return record

    async def _wait_turn(self) -> None:
        """Разносит начала запросов не чаще `REQUESTS_PER_MINUTE` в минуту."""
        loop = asyncio.get_running_loop()
        async with self._pace:
            delay = self._next_start - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_start = max(loop.time(), self._next_start) + 60 / REQUESTS_PER_MINUTE

    @property
    def cost(self) -> float:
        """Стоимость вызовов этого запуска (без кеша), $."""
        return (
            self.usage['prompt_tokens'] * PRICE_IN + self.usage['completion_tokens'] * PRICE_OUT
        ) / 1e6


def _parse_json(content: str) -> dict[str, Any] | None:
    match = re.search(r'\{.*\}', content, re.S)
    if match is None:
        return None
    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _excerpts(sample: Sample, corpus: Corpus) -> str:
    first = sample.evidence[0][0] if sample.evidence else ''
    chars = WINDOW_CHARS // max(1, len(sample.source_docs))
    blocks = []
    for doc in sample.source_docs:
        corpus.load(doc)
        # Окно ищем по фрагменту из этого документа, если он там есть.
        fragment = next(
            (g[0] for g in sample.evidence if evidence_in(g, corpus.normalized[doc])), first
        )
        blocks.append(f'### {doc}\n{corpus.window(doc, fragment, chars)}')
    return '\n\n'.join(blocks)


async def llm_check(sample: Sample, corpus: Corpus, checker: LlmChecker) -> dict[str, Any]:
    """Три вызова модели по одному вопросу.

    Args:
        sample: Вопрос.
        corpus: Тексты документов.
        checker: Клиент модели проверки.

    Returns:
        `review` (JSON-вердикт), `answer` (ответ модели), `compare` (JSON сравнения).
    """
    excerpts = _excerpts(sample, corpus)
    evidence = '\n'.join(f'- {" | ".join(g)}' for g in sample.evidence)
    review_user = (
        f'QUESTION: {sample.question}\n\nREFERENCE ANSWER: {sample.ground_truth}\n\n'
        f'EVIDENCE:\n{evidence}\n\nDOCUMENT EXCERPT:\n{excerpts}'
    )
    solve_user = f'DOCUMENT EXCERPTS:\n{excerpts}\n\nQUESTION: {sample.question}'
    review, solved = await asyncio.gather(
        checker.call(sample.id, 'review', REVIEW_PROMPT, review_user),
        checker.call(sample.id, 'solve', SOLVE_PROMPT, solve_user),
    )
    compare_user = (
        f'QUESTION: {sample.question}\n\nREFERENCE: {sample.ground_truth}\n\n'
        f'CANDIDATE: {solved["content"]}'
    )
    compare = await checker.call(sample.id, 'compare', COMPARE_PROMPT, compare_user)
    return {'review': review['parsed'], 'answer': solved['content'], 'compare': compare['parsed']}


# --- отчёт -------------------------------------------------------------------------------


@dataclass(slots=True)
class Result:
    """Итог проверок одного вопроса."""

    sample: Sample
    numbers: list[str]
    elsewhere: list[str]
    llm: dict[str, Any] | None = None

    @property
    def flags(self) -> list[str]:
        """Причины, по которым вопрос стоит посмотреть вручную."""
        flags = []
        if self.numbers:
            flags.append(f'числа не из фрагментов: {", ".join(self.numbers)}')
        if self.elsewhere:
            flags.append(f'эталон есть ещё в {len(self.elsewhere)} док.')
        if self.llm is not None:
            review = self.llm['review'] or {}
            compare = self.llm['compare'] or {}
            if not review:
                flags.append('LLM: не разобран вердикт')
            elif review.get('verdict') != 'ok':
                flags.append(f'LLM-вердикт: {review.get("verdict")}')
            for key, label in (
                ('answer_supported', 'ответ не следует из фрагментов'),
                ('evidence_sufficient', 'фрагментов не хватает'),
                ('question_clear', 'вопрос неоднозначен'),
            ):
                if review and review.get(key) is False:
                    flags.append(label)
            if review.get('document_conflict') is True:
                flags.append('в документе есть противоречие')
            if compare.get('match') != 'yes':
                flags.append(f'решение моделью: {compare.get("match", "?")}')
        return flags


def write_report(results: list[Result], llm_used: bool, cost: float | None) -> None:
    """Пишет markdown-отчёт со сводкой и списком помеченных вопросов.

    Args:
        results: Результаты по вопросам.
        llm_used: Выполнялась ли проверка LLM.
        cost: Стоимость вызовов этого запуска, $.
    """
    flagged = [r for r in results if r.flags]
    by_source = Counter(r.sample.metadata.get('source', '?') for r in results)
    flagged_by_source = Counter(r.sample.metadata.get('source', '?') for r in flagged)
    lines = [
        '# Автоматическая проверка вопросов',
        '',
        'Сгенерировано `python -m benchmarks.check_questions'
        + (' --llm`' if llm_used else '`')
        + '. Флаг — повод посмотреть вопрос вручную, а не вердикт об ошибке.',
        '',
        f'Проверено вопросов: {len(results)}; помечено: {len(flagged)}.',
        '',
        '| Источник | Вопросов | Помечено |',
        '|---|---|---|',
        *(f'| {s} | {n} | {flagged_by_source[s]} |' for s, n in sorted(by_source.items())),
        '',
    ]
    if cost is not None:
        lines += [f'Стоимость LLM-вызовов в этом запуске: ${cost:.3f}.', '']
    reasons = Counter(re.sub(r':.*', '', f) for r in flagged for f in r.flags)
    lines += ['## Причины', '', *(f'- {k}: {v}' for k, v in reasons.most_common()), '']
    lines += ['## Помеченные вопросы', '']
    for r in flagged:
        s = r.sample
        lines += [
            f'### `{s.id}`',
            '',
            f'- **Флаги:** {"; ".join(r.flags)}',
            f'- **Вопрос:** {s.question}',
            f'- **Эталон:** {s.ground_truth}',
        ]
        if r.elsewhere:
            lines.append(f'- **Эталон также в:** {", ".join(r.elsewhere[:5])}')
        if r.llm is not None:
            review = r.llm['review'] or {}
            compare = r.llm['compare'] or {}
            answer = re.sub(r'\s+', ' ', r.llm['answer']).strip()
            lines += [
                f'- **Замечание модели:** {review.get("issues") or "—"}',
                f'- **Ответ модели по документу:** {answer[:600]}',
                f'- **Сравнение:** {compare.get("match", "?")}; {compare.get("difference") or ""}',
            ]
        lines.append('')
    REPORT_PATH.write_text('\n'.join(lines), encoding='utf-8')


async def run(args: argparse.Namespace) -> int:
    """Выполняет проверки и пишет отчёт.

    Args:
        args: Аргументы CLI.

    Returns:
        Код возврата (0 — успех, даже если есть помеченные вопросы).
    """
    samples = [s for d in DOMAINS for s in read_samples(DATASETS_DIR / f'{d}.jsonl')]
    if args.source != 'all':
        samples = [
            s
            for s in samples
            if (s.metadata.get('source') == 'manual') == (args.source == 'manual')
        ]
    if args.ids:
        samples = [s for s in samples if s.id in set(args.ids)]
    if args.limit:
        samples = samples[: args.limit]

    corpus = Corpus()
    domain_docs = {d: corpus.domain_docs(d) for d in DOMAINS}
    results = [
        Result(s, unsupported_numbers(s), evidence_elsewhere(s, corpus, domain_docs[s.domain]))
        for s in samples
    ]

    checker = None
    if args.llm:
        settings = get_settings()
        client = AsyncOpenAI(
            base_url=f'{settings.litellm_url}/v1', api_key=settings.litellm_api_key
        )
        CHECKS_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = CHECKS_DIR / f'{args.model_tag}{"-reasoning" if args.reasoning else ""}.jsonl'
        checker = LlmChecker(client, cache_path, args.reasoning)
        try:
            checked = await asyncio.gather(*(llm_check(r.sample, corpus, checker) for r in results))
        finally:
            await client.close()
        for result, llm in zip(results, checked, strict=True):
            result.llm = llm
        logger.info(
            'LLM: %s вызовов, %s/%s токенов, ~$%.3f',
            checker.usage['calls'],
            checker.usage['prompt_tokens'],
            checker.usage['completion_tokens'],
            checker.cost,
        )

    write_report(results, args.llm, checker.cost if checker else None)
    flagged = sum(1 for r in results if r.flags)
    logger.info('проверено %s, помечено %s → %s', len(results), flagged, REPORT_PATH)
    return 0


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(prog='python -m benchmarks.check_questions')
    parser.add_argument('--llm', action='store_true', help='проверка моделью `check` (платно)')
    parser.add_argument('--reasoning', action='store_true', help='не отключать reasoning модели')
    parser.add_argument('--source', choices=('all', 'manual', 'auto'), default='all')
    parser.add_argument('--ids', nargs='*', help='проверить только эти вопросы')
    parser.add_argument('--limit', type=int, help='проверить первые N вопросов')
    parser.add_argument('--model-tag', default='gpt-5.6-luna', help='имя файла кеша ответов')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    logging.getLogger('httpx').setLevel(logging.WARNING)
    sys.exit(asyncio.run(run(args)))


if __name__ == '__main__':
    main()
