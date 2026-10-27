"""Парный бутстреп разности evidence recall двух систем: `python -m benchmarks.paired_diff`.

Системы отвечают на одни и те же вопросы, поэтому для утверждения «A лучше B» корректнее
бутстреп разности A − B по вопросам, чем сравнение отдельных интервалов (их перекрытие —
слишком консервативный критерий). Для каждого бюджета контекста считаются средняя разность,
95% интервал и доля бутстреп-выборок, где разность > 0. Результат —
`results/equal_budget/paired_diff.md` (против Dify) и `paired_diff_fastgpt.md` (против
FastGPT), а также `.csv`.
"""

import csv
import random
import statistics
from collections import defaultdict

from benchmarks.budget_recall import BUDGETS, OUT_DIR, truncate
from benchmarks.dataset import DOMAINS, Sample
from benchmarks.metrics import score_sample
from benchmarks.run_eval import RAW_DIR, _read_jsonl, load_samples

ITERATIONS = 5000
# (прогон, конфигурация, подпись) базовой системы → системы, которые с ней сравниваются,
# и имя файла отчёта. Базовые — лучшая конфигурация Dify и лучшая конфигурация FastGPT.
PROTOTYPES = (
    ('domain', 'hybrid_rerank', 'Прототип: чанкеры + гибрид + реранк'),
    ('domain', 'full', 'Полный прототип (parent-expansion)'),
)
COMPARISONS = (
    (
        ('dify_top24', 'dify_hybrid_rerank', 'Dify top-24: гибрид + реранк'),
        (
            *PROTOTYPES,
            ('naive', 'vector', 'Простой RAG'),
            ('fastgpt', 'fastgpt_vector', 'FastGPT: вектор'),
            ('anythingllm', 'anythingllm_top8', 'AnythingLLM: top-8'),
        ),
        'paired_diff',
    ),
    (('fastgpt', 'fastgpt_vector', 'FastGPT: вектор'), PROTOTYPES, 'paired_diff_fastgpt'),
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


def report(
    baseline: tuple[str, str, str],
    candidates: tuple[tuple[str, str, str], ...],
    stem: str,
    samples: list[Sample],
) -> str:
    """Парные разности `candidates` − `baseline`; пишет `<stem>.md` и `<stem>.csv`."""
    ids = {s.id for s in samples}
    domain_of = {s.id: s.domain for s in samples}
    base = recalls(baseline[0], baseline[1], ids)
    rows = []
    lines = [
        f'# Парные разности evidence recall против «{baseline[2]}»',
        '',
        f'{len(ids)} вопросов; разность = система − '
        f'«{baseline[2]}» по каждому вопросу, парный бутстреп ({ITERATIONS} выборок). '
        'P(>0) — доля выборок с положительной разностью: близко к 1 — система лучше, к 0 — хуже, '
        'около 0.5 — различия нет.',
        '',
    ]
    for run, config, label in candidates:
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
    with (OUT_DIR / f'{stem}.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(
            ['system', 'domain', 'budget_tokens', 'mean_diff', 'ci_low', 'ci_high', 'p_positive']
        )
        writer.writerows(rows)
    text = '\n'.join(lines)
    (OUT_DIR / f'{stem}.md').write_text(text, encoding='utf-8')
    return text


def main() -> None:
    """Считает парные разности для всех базовых систем и пишет отчёты."""
    samples = load_samples()
    for baseline, candidates, stem in COMPARISONS:
        if (RAW_DIR / f'{baseline[0]}.jsonl').exists():
            print(report(baseline, candidates, stem, samples))


if __name__ == '__main__':
    main()
