"""Парный бутстреп разности evidence recall двух систем: `python -m benchmarks.paired_diff`.

Системы отвечают на одни и те же вопросы, поэтому для утверждения «A лучше B» корректнее
бутстреп разности A − B по вопросам, чем сравнение отдельных интервалов (их перекрытие —
слишком консервативный критерий). Для каждого бюджета контекста считаются средняя разность,
95% интервал и доля бутстреп-выборок, где разность > 0. Результат —
`results/equal_budget/paired_diff.md` и `.csv`.
"""

import csv
import random
import statistics
from collections import defaultdict

from benchmarks.budget_recall import BUDGETS, truncate
from benchmarks.compare_subset import coverage
from benchmarks.dataset import DOMAINS
from benchmarks.metrics import score_sample
from benchmarks.run_eval import RAW_DIR, RESULTS_DIR, _read_jsonl, load_samples

OUT_DIR = RESULTS_DIR / 'equal_budget'
ITERATIONS = 5000
# (прогон, конфигурация, подпись): наши конфигурации против лучшей конфигурации Dify.
BASELINE = ('dify_top24', 'dify_hybrid_rerank', 'Dify top-24: гибрид + реранк')
CANDIDATES = (
    ('domain', 'hybrid_rerank', 'Наша: чанкеры + гибрид + реранк'),
    ('domain', 'full', 'Наша: полная (parent-expansion)'),
    ('naive', 'vector', 'Простой RAG'),
)


def recalls(run: str, config: str, ids: set[str]) -> dict[tuple[str, int], float]:
    """Evidence recall по (вопрос, бюджет)."""
    samples = {s.id: s for s in load_samples() if s.id in ids}
    result = {}
    for record in _read_jsonl(RAW_DIR / f'{run}.jsonl'):
        sample = samples.get(record['id'])
        if sample is None:
            continue
        contexts = [c['content'] for c in record['contexts'][config]]
        for budget in BUDGETS:
            cut = truncate(contexts, budget)
            result[(sample.id, budget)] = score_sample(sample, cut, [''] * len(cut))[
                'evidence_recall'
            ]
    return result


def paired(diffs: list[float], seed: int = 0) -> tuple[float, float, float, float]:
    """Средняя разность, 95% интервал и доля бутстреп-выборок с разностью > 0."""
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(statistics.fmean(rng.choices(diffs, k=n)) for _ in range(ITERATIONS))
    positive = sum(m > 0 for m in means) / ITERATIONS
    low, high = means[int(0.025 * ITERATIONS)], means[int(0.975 * ITERATIONS)]
    return statistics.fmean(diffs), low, high, positive


def main() -> None:
    """Считает парные разности и пишет отчёт."""
    done, _ = coverage()
    samples = [s for s in load_samples() if all(d in done for d in s.source_docs)]
    ids = {s.id for s in samples}
    domain_of = {s.id: s.domain for s in samples}
    base = recalls(BASELINE[0], BASELINE[1], ids)
    rows = []
    lines = [
        f'# Парные разности evidence recall против «{BASELINE[2]}»',
        '',
        f'{len(ids)} вопросов общего с Dify подмножества; разность = система − Dify по каждому '
        f'вопросу, парный бутстреп ({ITERATIONS} выборок). P(>0) — доля выборок с положительной '
        'разностью: близко к 1 — система лучше, к 0 — хуже, около 0.5 — различия нет.',
        '',
    ]
    for run, config, label in CANDIDATES:
        cand = recalls(run, config, ids)
        diffs: dict[tuple[str, int], list[float]] = defaultdict(list)
        for (qid, budget), value in cand.items():
            delta = value - base[(qid, budget)]
            diffs[('all', budget)].append(delta)
            diffs[(domain_of[qid], budget)].append(delta)
        lines += [f'## {label}', '', '| Домен | ' + ' | '.join(f'{b} ток.' for b in BUDGETS) + ' |']
        lines.append('|---' * (len(BUDGETS) + 1) + '|')
        for domain in ('all', *DOMAINS):
            cells = []
            for budget in BUDGETS:
                mean, low, high, positive = paired(diffs[(domain, budget)])
                rows.append([label, domain, budget, mean, low, high, positive])
                cells.append(f'{mean:+.3f} [{low:+.2f}…{high:+.2f}], P(>0)={positive:.2f}')
            lines.append(f'| {domain} | ' + ' | '.join(cells) + ' |')
        lines.append('')
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with (OUT_DIR / 'paired_diff.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(
            ['system', 'domain', 'budget_tokens', 'mean_diff', 'ci_low', 'ci_high', 'p_positive']
        )
        writer.writerows(rows)
    report = '\n'.join(lines)
    (OUT_DIR / 'paired_diff.md').write_text(report, encoding='utf-8')
    print(report)


if __name__ == '__main__':
    main()
