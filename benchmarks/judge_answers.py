"""Оценка ответов LLM-судьёй: `python -m benchmarks.judge_answers domain:full naive:vector ...`.

Аргумент — `<прогон>:<конфигурация>`: контексты из `results/raw/<прогон>.jsonl`, ответы из
`results/raw/<прогон>-answers-<конфигурация>.jsonl`. Судья — алиас `judge` (общий для всех
систем) с отключённым reasoning. За один вызов он:
- выделяет утверждения ответа и считает, сколько из них подтверждено контекстами
  (Faithfulness по методике RAGAS: доля подтверждённых утверждений);
- сравнивает ответ с эталоном: верно / частично / неверно (Answer correctness: 1 / 0.5 / 0).

Отказ («нет данных») не входит в Faithfulness (утверждений нет), а в правильности считается 0.
Вердикты кешируются в `results/raw/judge-<прогон>-<конфигурация>.jsonl`; сводка с 95% CI —
`results/judge-summary.csv` и `results/judge.md`.
"""

import argparse
import asyncio
import csv
import json
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI, RateLimitError

from app.config import get_settings
from app.generation import format_contexts
from app.retrieval.hybrid import RetrievedChunk
from benchmarks.dataset import DOMAINS
from benchmarks.metrics import bootstrap_ci
from benchmarks.run_eval import RAW_DIR, RESULTS_DIR, _read_jsonl, load_samples

logger = logging.getLogger('benchmarks.judge')

REQUESTS_PER_MINUTE = 18
CONCURRENCY = 4
RETRIES = 6
BACKOFF_S = 30.0
# Ограничение длины контекстов в промпте судьи (символов), чтобы parent-таблицы не раздували цену.
MAX_CONTEXT_CHARS = 60_000

PROMPT = """You evaluate an answer produced by a retrieval-augmented assistant.
Inputs: QUESTION, numbered CONTEXTS retrieved by the system, the ANSWER, and a REFERENCE answer.

1. Split the ANSWER into atomic factual claims (ignore citation markers like [1] and phrases
   such as "according to the documents"). If the answer only says that the information is
   not available, it has 0 claims and refusal = true.
2. For each claim decide whether it is directly supported by the CONTEXTS (not by your own
   knowledge). Count supported claims.
3. Compare the ANSWER with the REFERENCE: "correct" if it contains the key facts of the
   reference (rounding and wording may differ), "partial" if some key facts are missing or
   wrong, "incorrect" otherwise (including refusals).

Reply with JSON only:
{"claims": <int>, "supported": <int>, "refusal": true|false,
 "correctness": "correct"|"partial"|"incorrect", "note": "<short reason>"}"""

CORRECTNESS = {'correct': 1.0, 'partial': 0.5, 'incorrect': 0.0}


class Pacer:
    """Не больше `REQUESTS_PER_MINUTE` стартов запросов в минуту."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        """Ждёт своей очереди."""
        loop = asyncio.get_running_loop()
        async with self._lock:
            delay = self._next - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)
            self._next = max(loop.time(), self._next) + 60 / REQUESTS_PER_MINUTE


def _parse(content: str) -> dict[str, Any] | None:
    match = re.search(r'\{.*\}', content, re.S)
    try:
        parsed = json.loads(match.group()) if match else None
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def judge_one(
    llm: AsyncOpenAI,
    model: str,
    pacer: Pacer,
    semaphore: asyncio.Semaphore,
    question: str,
    reference: str,
    contexts: list[dict[str, Any]],
    answer: str,
) -> dict[str, Any]:
    """Один вызов судьи; возвращает разобранный вердикт и сырой ответ."""
    chunks = [RetrievedChunk(metadata={}, **c) for c in contexts]
    block = format_contexts(chunks)[:MAX_CONTEXT_CHARS]
    user = (
        f'QUESTION: {question}\n\nCONTEXTS:\n{block}\n\nANSWER: {answer}\n\nREFERENCE: {reference}'
    )
    async with semaphore:
        for attempt in range(1, RETRIES + 1):
            await pacer.wait()
            try:
                response = await llm.chat.completions.create(
                    model=model,
                    messages=[
                        {'role': 'system', 'content': PROMPT},
                        {'role': 'user', 'content': user},
                    ],
                    temperature=0,
                    max_tokens=400,
                    extra_body={'reasoning': {'enabled': False}},
                )
                break
            except RateLimitError:
                if attempt == RETRIES:
                    raise
                await asyncio.sleep(BACKOFF_S)
    content = response.choices[0].message.content or ''
    usage = response.usage
    return {
        'verdict': _parse(content),
        'raw': content,
        'prompt_tokens': usage.prompt_tokens if usage else 0,
        'completion_tokens': usage.completion_tokens if usage else 0,
    }


async def judge_run(target: str, llm: AsyncOpenAI, model: str, pacer: Pacer) -> Path:
    """Оценивает ответы одной конфигурации (с продолжением по кешу)."""
    run, config = target.split(':')
    samples = {s.id: s for s in load_samples()}
    contexts = {r['id']: r['contexts'][config] for r in _read_jsonl(RAW_DIR / f'{run}.jsonl')}
    answers = {r['id']: r['answer'] for r in _read_jsonl(RAW_DIR / f'{run}-answers-{config}.jsonl')}
    out = RAW_DIR / f'judge-{run}-{config}.jsonl'
    done = {r['id'] for r in _read_jsonl(out)}
    todo = [i for i in answers if i in samples and i in contexts and i not in done]
    logger.info('%s: %s ответов к оценке (%s уже есть)', target, len(todo), len(done))
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def one(sample_id: str) -> None:
        sample = samples[sample_id]
        result = await judge_one(
            llm,
            model,
            pacer,
            semaphore,
            sample.question,
            sample.ground_truth,
            contexts[sample_id],
            answers[sample_id],
        )
        record = {'id': sample_id, 'domain': sample.domain, **result}
        with out.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    await asyncio.gather(*(one(i) for i in todo))
    return out


def summarize(targets: list[str], ids: set[str] | None = None, out_dir: Path = RESULTS_DIR) -> str:
    """Сводка по кешам вердиктов (только вопросы из `ids`, если заданы): CSV и markdown."""
    rows = []
    lines = [
        '# Оценка ответов LLM-судьёй',
        '',
        'Faithfulness — доля утверждений ответа, подтверждённых контекстами (без отказов); '
        'correctness — совпадение с эталоном (1 / 0.5 / 0, отказ = 0); refusal — доля отказов. '
        'Среднее [95% bootstrap CI].',
        '',
        '| Прогон:конфигурация | Домен | n | faithfulness | correctness | refusal |',
        '|---|---|---|---|---|---|',
    ]
    for target in targets:
        run, config = target.split(':')
        records = _read_jsonl(RAW_DIR / f'judge-{run}-{config}.jsonl')
        if ids is not None:
            records = [r for r in records if r['id'] in ids]
        values: dict[tuple[str, str], list[float]] = defaultdict(list)
        for r in records:
            v = r['verdict'] or {}
            claims = int(v.get('claims') or 0)
            refusal = bool(v.get('refusal')) or claims == 0
            for domain in (r['domain'], 'all'):
                if not refusal:
                    values[(domain, 'faithfulness')].append(
                        min(1.0, int(v.get('supported') or 0) / claims)
                    )
                values[(domain, 'correctness')].append(
                    CORRECTNESS.get(str(v.get('correctness')), 0.0)
                )
                values[(domain, 'refusal')].append(float(refusal))
        for domain in (*DOMAINS, 'all'):
            cells = []
            for metric in ('faithfulness', 'correctness', 'refusal'):
                mean, low, high = bootstrap_ci(values[(domain, metric)])
                rows.append(
                    [run, config, domain, metric, len(values[(domain, metric)]), mean, low, high]
                )
                cells.append(f'{mean:.3f} [{low:.2f}–{high:.2f}]')
            n = len(values[(domain, 'correctness')])
            lines.append(f'| {target} | {domain} | {n} | ' + ' | '.join(cells) + ' |')
    with (out_dir / 'judge-summary.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['run', 'config', 'domain', 'metric', 'n', 'mean', 'ci_low', 'ci_high'])
        writer.writerows(rows)
    report = '\n'.join(lines) + '\n'
    (out_dir / 'judge.md').write_text(report, encoding='utf-8')
    return report


async def run(targets: list[str], summary_only: bool) -> int:
    """Оценивает конфигурации и пишет сводку."""
    if not summary_only:
        settings = get_settings()
        llm = AsyncOpenAI(base_url=f'{settings.litellm_url}/v1', api_key=settings.litellm_api_key)
        pacer = Pacer()
        try:
            for target in targets:
                await judge_run(target, llm, settings.judge_model, pacer)
        finally:
            await llm.close()
    print(summarize(targets))
    return 0


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(prog='python -m benchmarks.judge_answers')
    parser.add_argument('targets', nargs='+', help='<прогон>:<конфигурация>, напр. domain:full')
    parser.add_argument('--summary-only', action='store_true')
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s'
    )
    for noisy in ('httpx', 'httpx2', 'openai'):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    sys.exit(asyncio.run(run(args.targets, args.summary_only)))


if __name__ == '__main__':
    main()
