"""Анализ чувствительности к ошибкам эталонов: `python -m benchmarks.sensitivity`.

При ручной проверке (`datasets/check_report.md`) в исходных разметках CUAD и FinQA найдены
вопросы с ошибочными эталонами. Сами датасеты не исправляются, чтобы оставаться
сопоставимыми с другими работами. Вместо этого основные сравнения пересчитываются без этих
вопросов: если выводы не меняются, ошибки разметки на них не влияют. Результат —
`results/sensitivity.md`.
"""

import csv
from collections import defaultdict

from benchmarks.budget_recall import BUDGETS
from benchmarks.compare_subset import coverage
from benchmarks.judge_answers import CORRECTNESS
from benchmarks.metrics import bootstrap_ci
from benchmarks.paired_diff import paired, recalls
from benchmarks.run_eval import RAW_DIR, RESULTS_DIR, _read_jsonl, load_samples

REPORT_PATH = RESULTS_DIR / 'sensitivity.md'

# Вопросы с ошибочным эталоном в исходной разметке (разбор — в check_report.md).
EXCLUDED = {
    'finqa-abmd_2005_page_29.pdf-1': 'арифметическая ошибка: по программе FinQA 5,85%, не 5,38%',
    'finqa-bll_2006_page_67.pdf-1': 'ответ не сходится с программой FinQA (32,4%, не 32,2%)',
    'finqa-fis_2006_page_31.pdf-1': 'бессмысленный знаменатель, вопрос неоднозначен',
    'finqa-awk_2012_page_117.pdf-1': 'сумма остатков за разные годы, неверные единицы',
    'cuad-americasshoppingmallinc_12_10_1999-ex-10-cap-on-liability': (
        'платёж при расторжении размечен как ограничение ответственности'
    ),
    'cuad-atmosenergycorp_11_22_2002-ex-10.17-tran-minimum-commitment': (
        'эталон — обрывок незаполненной формы'
    ),
}

RETRIEVAL_METRICS = ('evidence_recall', 'mrr', 'ap')
ANSWER_METRICS = ('correctness', 'faithfulness')
PROTOTYPE = ('domain', 'full', 'Полный прототип')
# Набор → системы (прогон, конфигурация, подпись). Dify сравнивается на своём подмножестве
# (вопросы, все документы которых есть в его индексе; см. compare_subset).
SCOPES = {
    'Полный набор': (
        PROTOTYPE,
        ('domain', 'hybrid_rerank', 'Прототип без parent-expansion'),
        ('naive', 'vector', 'Простой RAG'),
        ('fastgpt', 'fastgpt_vector', 'FastGPT: вектор'),
        ('fastgpt', 'fastgpt_hybrid', 'FastGPT: гибрид'),
        ('anythingllm', 'anythingllm_default', 'AnythingLLM: top-4'),
        ('anythingllm', 'anythingllm_top8', 'AnythingLLM: top-8'),
    ),
    'Подмножество Dify': (
        PROTOTYPE,
        ('naive', 'vector', 'Простой RAG'),
        ('dify', 'dify_vector', 'Dify top-8: вектор'),
        ('dify', 'dify_hybrid_rerank', 'Dify top-8: гибрид + реранк'),
        ('dify_top24', 'dify_hybrid_rerank', 'Dify top-24: гибрид + реранк'),
    ),
}
BUDGET_BASELINE = ('dify_top24', 'dify_hybrid_rerank')


def retrieval_values(run: str, config: str) -> dict[str, dict[str, float]]:
    """Метрики поиска по вопросам: метрика → {id: значение} (из `<прогон>-scores.csv`)."""
    path = RESULTS_DIR / f'{run}-scores.csv'
    if not path.exists():
        path = RESULTS_DIR / 'equal_budget' / f'{run}-scores.csv'
    values: dict[str, dict[str, float]] = defaultdict(dict)
    with path.open(encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['config'] == config and row['metric'] in RETRIEVAL_METRICS:
                values[row['metric']][row['id']] = float(row['value'])
    return values


def answer_values(run: str, config: str) -> dict[str, dict[str, float]]:
    """Оценки судьи по вопросам; faithfulness — только для ответов без отказа."""
    path = RAW_DIR / f'judge-{run}-{config}.jsonl'
    values: dict[str, dict[str, float]] = defaultdict(dict)
    if not path.exists():
        return values
    for record in _read_jsonl(path):
        verdict = record['verdict'] or {}
        claims = int(verdict.get('claims') or 0)
        values['correctness'][record['id']] = CORRECTNESS.get(str(verdict.get('correctness')), 0.0)
        if claims and not verdict.get('refusal'):
            supported = int(verdict.get('supported') or 0)
            values['faithfulness'][record['id']] = min(1.0, supported / claims)
    return values


def _mean(values: dict[str, float], ids: set[str]) -> tuple[float, float, float, int]:
    picked = [v for k, v in values.items() if k in ids]
    return (*bootstrap_ci(picked), len(picked))


def _pair(
    a: dict[str, float], b: dict[str, float], ids: set[str]
) -> tuple[float, float, float, float]:
    diffs = [a[i] - b[i] for i in sorted(ids) if i in a and i in b]
    return paired(diffs) if diffs else (0.0, 0.0, 0.0, 0.0)


def _fmt_pair(result: tuple[float, float, float, float]) -> str:
    mean, low, high, positive = result
    return f'{mean:+.3f} [{low:+.2f}…{high:+.2f}], P(>0)={positive:.2f}'


def main() -> None:
    """Пересчитывает сравнения без вопросов с ошибочными эталонами и пишет отчёт."""
    samples = load_samples()
    done, _ = coverage()
    scope_ids = {
        'Полный набор': {s.id for s in samples},
        'Подмножество Dify': {s.id for s in samples if all(d in done for d in s.source_docs)},
    }
    lines = [
        '# Анализ чувствительности к ошибкам эталонов',
        '',
        'Сравнения пересчитаны без вопросов, у которых ручная проверка нашла ошибку в исходной '
        'разметке CUAD/FinQA. Датасет не меняется. «Все» — исходный набор, «без ошибочных» — '
        'без этих вопросов. Среднее [95% bootstrap CI]; разности — парный бутстреп '
        'по вопросам, P(>0) — доля выборок, где прототип лучше.',
        '',
        '## Исключённые вопросы',
        '',
        '| Вопрос | Причина | Полный набор | Подмножество Dify |',
        '|---|---|---|---|',
    ]
    for qid, reason in EXCLUDED.items():
        marks = ['да' if qid in scope_ids[s] else 'нет' for s in SCOPES]
        lines.append(f'| `{qid}` | {reason} | ' + ' | '.join(marks) + ' |')
    lines.append('')

    for scope, systems in SCOPES.items():
        full = scope_ids[scope]
        clean = full - EXCLUDED.keys()
        data = {
            (run, config): {**retrieval_values(run, config), **answer_values(run, config)}
            for run, config, _ in systems
        }
        lines += [
            f'## {scope}: {len(full)} → {len(clean)} вопросов',
            '',
            '| Метрика | Система | Все | Без ошибочных | Δ |',
            '|---|---|---|---|---|',
        ]
        for metric in (*RETRIEVAL_METRICS, *ANSWER_METRICS):
            for run, config, label in systems:
                values = data[(run, config)].get(metric)
                if not values:
                    continue
                before = _mean(values, full)
                after = _mean(values, clean)
                lines.append(
                    f'| {metric} | {label} | {before[0]:.3f} [{before[1]:.2f}–{before[2]:.2f}] '
                    f'| {after[0]:.3f} [{after[1]:.2f}–{after[2]:.2f}] '
                    f'| {after[0] - before[0]:+.3f} |'
                )
        lines += [
            '',
            f'### Разность «{PROTOTYPE[2]} − система»',
            '',
            '| Метрика | Система | Все | Без ошибочных |',
            '|---|---|---|---|',
        ]
        proto = data[PROTOTYPE[:2]]
        for metric in (*RETRIEVAL_METRICS, *ANSWER_METRICS):
            for run, config, label in systems[1:]:
                other = data[(run, config)].get(metric)
                if not other or metric not in proto:
                    continue
                lines.append(
                    f'| {metric} | {label} | {_fmt_pair(_pair(proto[metric], other, full))} '
                    f'| {_fmt_pair(_pair(proto[metric], other, clean))} |'
                )
        lines.append('')

    # Главный вывод про Dify — равный бюджет контекста: разность evidence recall по бюджетам.
    subset = scope_ids['Подмножество Dify']
    base = recalls(*BUDGET_BASELINE, subset)
    cand = recalls(*PROTOTYPE[:2], subset)
    lines += [
        '## Равный бюджет контекста: прототип − Dify top-24 (гибрид + реранк)',
        '',
        'Evidence recall при обрезке контекста до N токенов (как в `equal_budget/paired_diff.md`).',
        '',
        '| Бюджет | Все | Без ошибочных |',
        '|---|---|---|',
    ]
    for budget in BUDGETS:
        cells = []
        for ids in (subset, subset - EXCLUDED.keys()):
            diffs = [cand[(i, budget)] - base[(i, budget)] for i in sorted(ids)]
            cells.append(_fmt_pair(paired(diffs)))
        lines.append(f'| {budget} ток. | ' + ' | '.join(cells) + ' |')
    lines.append('')

    REPORT_PATH.write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))
    print(f'\nотчёт → {REPORT_PATH}; исключено {len(EXCLUDED)}')


if __name__ == '__main__':
    main()
