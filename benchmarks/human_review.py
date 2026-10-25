"""Ручная разметка ответов для калибровки LLM-судьи: `python -m benchmarks.human_review`.

Шаг `sample` собирает `benchmarks/review/answers_review.xlsx`: стратифицированную выборку
пар «вопрос — ответ системы» без оценок судьи и без названия системы (ключ — в
`answers_key.json`). Шаг `agreement` читает заполненный файл и сравнивает разметку
с вердиктами судьи: доля совпадений и каппа Коэна по отказам, правильности и опоре
на контекст. Отчёт — `results/judge_agreement.md`.

Вопросы CUAD в выборку не входят: их эталоны — юридические формулировки на английском
по праву США, разметчик не может оценить их надёжно (ограничение калибровки).
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from benchmarks.dataset import ROOT, Sample
from benchmarks.judge_answers import MAX_CONTEXT_CHARS
from benchmarks.run_eval import RAW_DIR, RESULTS_DIR, _read_jsonl, load_samples

REVIEW_DIR = ROOT / 'review'
XLSX_PATH = REVIEW_DIR / 'answers_review.xlsx'
KEY_PATH = REVIEW_DIR / 'answers_key.json'
REPORT_PATH = RESULTS_DIR / 'judge_agreement.md'

SEED = 20261025
SYSTEMS = (
    ('domain', 'full'),
    ('naive', 'vector'),
    ('dify', 'dify_vector'),
    ('dify', 'dify_hybrid_rerank'),
)
# Страта → число вопросов; страта — источник вопроса (+ домен для ручных).
STRATA = {'ru-contracts': 9, 'ru-tables': 9, 'code': 6, 'finqa': 6}
# Не больше стольких отказов в выборке: отказ размечается тривиально и не калибрует судью.
MAX_REFUSALS = 5
REFUSAL_PREFIXES = ('нет данных', 'no data')
# Ограничение Excel на длину ячейки.
MAX_CELL_CHARS = 32_000

YES_NO = ('да', 'нет')
CORRECTNESS = ('верно', 'частично', 'неверно')
CORRECTNESS_EN = {'correct': 'верно', 'partial': 'частично', 'incorrect': 'неверно'}
COLUMNS = (
    ('№', 6),
    ('Домен', 10),
    ('Вопрос', 50),
    ('Эталон', 50),
    ('Ответ системы', 70),
    ('Отказ', 10),
    ('Правильность', 14),
    ('Все утверждения подтверждены контекстом', 18),
    ('Комментарий', 40),
)
INPUT_COLUMNS = {'Отказ': 6, 'Правильность': 7, 'Опора': 8, 'Комментарий': 9}

INSTRUCTION = """Разметка ответов для калибровки LLM-судьи

На листе «Разметка» — {n} ответов разных систем (система скрыта). Контексты, которые
система получила, — на листе «Контексты» (по номеру строки). Судья видел те же контексты
(первые {max_chars} символов).

Для каждого ответа заполните три колонки (выпадающие списки):

1. Отказ — «да», если ответ только сообщает, что данных нет; иначе «нет».
2. Правильность — сравнение ответа с эталоном:
   • верно — ответ содержит ключевые факты эталона (округление и формулировки могут отличаться);
   • частично — часть ключевых фактов отсутствует или неверна;
   • неверно — ключевые факты неверны или отсутствуют; отказ — всегда «неверно».
   Лишние верные подробности сверх эталона не снижают оценку.
3. Все утверждения подтверждены контекстом — «да», если каждое фактическое утверждение
   ответа можно найти в контекстах (а не взять из общих знаний); «нет», если хотя бы одно
   утверждение не подтверждено. Для отказов оставьте пустым.

Оценивайте по тексту эталона и контекстов, не заглядывая в оценки судьи.
Колонка «Комментарий» — по желанию (например, если эталон кажется спорным).
"""


def _stratum(sample: Sample) -> str | None:
    source = sample.metadata.get('source')
    if source == 'manual':
        return 'code' if sample.domain == 'code' else f'ru-{sample.domain}'
    return 'finqa' if source == 'finqa' else None


def _is_refusal(answer: str) -> bool:
    return answer.strip().lower().startswith(REFUSAL_PREFIXES)


def _contexts(run: str, config: str) -> dict[str, list[dict[str, Any]]]:
    return {r['id']: r['contexts'][config] for r in _read_jsonl(RAW_DIR / f'{run}.jsonl')}


def _answers(run: str, config: str) -> dict[str, str]:
    path = RAW_DIR / f'{run}-answers-{config}.jsonl'
    return {r['id']: r['answer'] for r in _read_jsonl(path)}


def draw() -> list[dict[str, Any]]:
    """Выбирает пары «вопрос — система»: каждый вопрос один раз, системы по кругу.

    Returns:
        Элементы выборки с вопросом, эталоном, ответом и контекстами.
    """
    rng = random.Random(SEED)
    samples = load_samples()
    answers = {s: _answers(*s) for s in SYSTEMS}
    contexts = {s: _contexts(*s) for s in SYSTEMS}
    items: list[dict[str, Any]] = []
    refusals = 0
    turn = 0
    for stratum, size in STRATA.items():
        pool = [s for s in samples if _stratum(s) == stratum]
        rng.shuffle(pool)
        taken = 0
        for sample in pool:
            if taken == size:
                break
            # Пробуем системы по кругу, пока не найдётся ответ, подходящий по лимиту отказов.
            for shift in range(len(SYSTEMS)):
                system = SYSTEMS[(turn + shift) % len(SYSTEMS)]
                answer = answers[system].get(sample.id)
                if answer is None or sample.id not in contexts[system]:
                    continue
                refusal = _is_refusal(answer)
                if refusal and refusals >= MAX_REFUSALS:
                    continue
                refusals += refusal
                turn += shift + 1
                taken += 1
                items.append(
                    {
                        'id': sample.id,
                        'run': system[0],
                        'config': system[1],
                        'domain': sample.domain,
                        'question': sample.question,
                        'reference': sample.ground_truth,
                        'answer': answer,
                        'contexts': contexts[system][sample.id],
                    }
                )
                break
    rng.shuffle(items)
    return items


def _wrap(cell: Any) -> None:
    cell.alignment = Alignment(wrap_text=True, vertical='top')


def write_xlsx(items: list[dict[str, Any]], path: Path) -> None:
    """Пишет файл разметки: инструкция, таблица разметки, контексты.

    Args:
        items: Элементы выборки (в порядке номеров).
        path: Куда сохранить xlsx.
    """
    wb = Workbook()
    info = wb.active
    assert info is not None
    info.title = 'Инструкция'
    text = INSTRUCTION.format(n=len(items), max_chars=MAX_CONTEXT_CHARS)
    for row, line in enumerate(text.splitlines(), start=1):
        info.cell(row=row, column=1, value=line)
    info['A1'].font = Font(bold=True, size=13)
    info.column_dimensions['A'].width = 110

    sheet = wb.create_sheet('Разметка')
    header_fill = PatternFill('solid', fgColor='DDDDDD')
    input_fill = PatternFill('solid', fgColor='FFF2CC')
    for col, (title, width) in enumerate(COLUMNS, start=1):
        cell = sheet.cell(row=1, column=col, value=title)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        _wrap(cell)
        sheet.column_dimensions[cell.column_letter].width = width
    sheet.freeze_panes = 'C2'
    for n, item in enumerate(items, start=1):
        values = [n, item['domain'], item['question'], item['reference'], item['answer']]
        for col, value in enumerate(values, start=1):
            _wrap(sheet.cell(row=n + 1, column=col, value=str(value)[:MAX_CELL_CHARS]))
        for col in INPUT_COLUMNS.values():
            cell = sheet.cell(row=n + 1, column=col)
            cell.fill = input_fill
            _wrap(cell)
    last = len(items) + 1
    for col, options in ((6, YES_NO), (7, CORRECTNESS), (8, YES_NO)):
        validation = DataValidation(type='list', formula1=f'"{",".join(options)}"')
        letter = sheet.cell(row=1, column=col).column_letter
        validation.add(f'{letter}2:{letter}{last}')
        sheet.add_data_validation(validation)

    ctx_sheet = wb.create_sheet('Контексты')
    for col, (title, width) in enumerate((('№', 6), ('Фрагмент', 10), ('Текст', 140)), 1):
        cell = ctx_sheet.cell(row=1, column=col, value=title)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        ctx_sheet.column_dimensions[cell.column_letter].width = width
    ctx_sheet.freeze_panes = 'A2'
    row = 2
    for n, item in enumerate(items, start=1):
        budget = MAX_CONTEXT_CHARS
        for k, ctx in enumerate(item['contexts'], start=1):
            if budget <= 0:
                break
            title = ctx.get('title') or ctx['source']
            text = f'{title} ({ctx["source"]})\n{ctx["content"]}'[:budget]
            budget -= len(text)
            ctx_sheet.cell(row=row, column=1, value=n)
            ctx_sheet.cell(row=row, column=2, value=f'[{k}]')
            _wrap(ctx_sheet.cell(row=row, column=3, value=text[:MAX_CELL_CHARS]))
            row += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def sample_cmd(force: bool) -> None:
    """Собирает выборку и пишет xlsx и ключ (не перезаписывает без `force`)."""
    if XLSX_PATH.exists() and not force:
        raise SystemExit(f'{XLSX_PATH} уже есть (возможно, с разметкой); --force перезапишет')
    items = draw()
    write_xlsx(items, XLSX_PATH)
    key = [{k: item[k] for k in ('id', 'run', 'config')} for item in items]
    KEY_PATH.write_text(json.dumps(key, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    by = Counter(f'{i["run"]}:{i["config"]}' for i in items)
    refusals = sum(_is_refusal(i['answer']) for i in items)
    print(f'{len(items)} ответов → {XLSX_PATH}; системы: {dict(by)}; отказов: {refusals}')


def cohen_kappa(pairs: list[tuple[str, str]], weights: dict[str, float] | None = None) -> float:
    """Каппа Коэна для пар меток; с `weights` — линейно взвешенная (метка → число).

    Args:
        pairs: Пары (человек, судья).
        weights: Числовые значения порядковых меток; `None` — невзвешенная каппа.

    Returns:
        Каппа; `nan`, если ожидаемое согласие равно 1 (все метки одинаковые).
    """
    labels = sorted({label for pair in pairs for label in pair})
    n = len(pairs)
    if n == 0:
        return float('nan')
    span = (max(weights.values()) - min(weights.values())) if weights else 1.0

    def disagreement(a: str, b: str) -> float:
        if weights is None:
            return float(a != b)
        return abs(weights[a] - weights[b]) / span

    human = Counter(a for a, _ in pairs)
    judge = Counter(b for _, b in pairs)
    observed = sum(disagreement(a, b) for a, b in pairs) / n
    expected = sum(human[a] * judge[b] * disagreement(a, b) for a in labels for b in labels) / (
        n * n
    )
    return float('nan') if expected == 0 else 1 - observed / expected


def _norm(value: Any) -> str:
    return str(value or '').strip().lower()


def agreement_cmd() -> None:
    """Сравнивает ручную разметку с вердиктами судьи и пишет отчёт."""
    key = json.loads(KEY_PATH.read_text(encoding='utf-8'))
    sheet = load_workbook(XLSX_PATH)['Разметка']
    verdicts: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for run, config in SYSTEMS:
        records = _read_jsonl(RAW_DIR / f'judge-{run}-{config}.jsonl')
        verdicts[(run, config)] = {r['id']: r['verdict'] or {} for r in records}

    refusal: list[tuple[str, str]] = []
    correctness: list[tuple[str, str]] = []
    support: list[tuple[str, str]] = []
    rows = []
    support_rows = []
    for n, item in enumerate(key, start=1):
        cells = {
            name: _norm(sheet.cell(row=n + 1, column=col).value)
            for name, col in INPUT_COLUMNS.items()
        }
        if not cells['Правильность']:
            continue
        v = verdicts[(item['run'], item['config'])][item['id']]
        claims = int(v.get('claims') or 0)
        j_refusal = 'да' if bool(v.get('refusal')) or claims == 0 else 'нет'
        j_correct = CORRECTNESS_EN.get(str(v.get('correctness')), 'неверно')
        j_support = 'да' if claims and int(v.get('supported') or 0) >= claims else 'нет'
        refusal.append((cells['Отказ'] or 'нет', j_refusal))
        correctness.append((cells['Правильность'], j_correct))
        note = str(v.get('note', '')).replace('|', '/')[:200]
        if cells['Опора'] and j_refusal == 'нет':
            support.append((cells['Опора'], j_support))
            if cells['Опора'] != j_support:
                support_rows.append(
                    f'| {n} | `{item["id"]}` | {cells["Опора"]} | {j_support} '
                    f'({v.get("supported")}/{claims}) | {note} |'
                )
        if cells['Правильность'] != j_correct:
            rows.append(
                f'| {n} | `{item["id"]}` | {cells["Правильность"]} | {j_correct} | {note} |'
            )

    def line(name: str, pairs: list[tuple[str, str]], weighted: bool = False) -> str:
        agree = sum(a == b for a, b in pairs) / len(pairs) if pairs else float('nan')
        kappa = cohen_kappa(pairs)
        cell = f'| {name} | {len(pairs)} | {agree:.2f} | {kappa:.2f} |'
        if weighted:
            w = cohen_kappa(pairs, {'неверно': 0.0, 'частично': 0.5, 'верно': 1.0})
            cell += f' {w:.2f} |'
        else:
            cell += ' — |'
        return cell

    matrix = Counter(correctness)
    report = [
        '# Согласие LLM-судьи с ручной разметкой',
        '',
        f'Выборка: `{XLSX_PATH.relative_to(ROOT.parent)}` (CUAD не входит). '
        'Каппа Коэна: < 0.4 — слабое, 0.4–0.6 — умеренное, 0.6–0.8 — существенное, '
        '> 0.8 — почти полное согласие.',
        '',
        '| Показатель | n | Доля совпадений | Каппа | Взвешенная каппа |',
        '|---|---|---|---|---|',
        line('Отказ', refusal),
        line('Правильность', correctness, weighted=True),
        line('Все утверждения подтверждены', support),
        '',
        '## Правильность: человек (строки) × судья (столбцы)',
        '',
        '| | ' + ' | '.join(CORRECTNESS) + ' |',
        '|---|---|---|---|',
        *(
            f'| {a} | ' + ' | '.join(str(matrix[(a, b)]) for b in CORRECTNESS) + ' |'
            for a in CORRECTNESS
        ),
        '',
        '## Расхождения по правильности',
        '',
        '| № | Вопрос | Человек | Судья | Обоснование судьи |',
        '|---|---|---|---|---|',
        *rows,
        '',
        '## Расхождения по опоре на контекст',
        '',
        '| № | Вопрос | Человек | Судья (подтверждено/утверждений) | Обоснование судьи |',
        '|---|---|---|---|---|',
        *support_rows,
        '',
    ]
    REPORT_PATH.write_text('\n'.join(report), encoding='utf-8')
    print('\n'.join(report))


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(prog='python -m benchmarks.human_review')
    parser.add_argument('step', choices=('sample', 'agreement'))
    parser.add_argument('--force', action='store_true', help='перезаписать файл разметки')
    args = parser.parse_args()
    if args.step == 'sample':
        sample_cmd(args.force)
    else:
        agreement_cmd()


if __name__ == '__main__':
    main()
