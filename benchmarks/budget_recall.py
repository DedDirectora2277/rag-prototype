"""Полнота при равном бюджете контекста: `python -m benchmarks.budget_recall`.

Системы отдают генератору разный объём текста (Dify — мелкие сегменты, parent-expansion —
разделы и таблицы целиком), поэтому evidence recall на top-8 частично отражает размер
контекста. Здесь контексты каждой системы обрезаются до бюджета в N токенов в порядке
ранжирования (последний контекст обрезается), и evidence recall пересчитывается.
Результат — `<out-dir>/budget_recall.csv` и `.md` (по умолчанию `results/equal_budget/`).
Прогоны, сырых результатов которых нет (например, `dify_top24`), пропускаются.
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from app.chunkers.base import get_encoding
from benchmarks.dataset import DOMAINS
from benchmarks.metrics import bootstrap_ci, score_sample
from benchmarks.run_eval import RAW_DIR, RESULTS_DIR, _read_jsonl, load_samples

OUT_DIR = RESULTS_DIR / 'equal_budget'
BUDGETS = (500, 1000, 2000, 4000, 8000)
SYSTEMS = (
    ('naive', 'vector', 'Простой RAG'),
    ('dify', 'dify_vector', 'Dify: вектор'),
    ('dify', 'dify_hybrid_rerank', 'Dify: гибрид + реранк'),
    ('dify_top24', 'dify_vector', 'Dify top-24: вектор'),
    ('dify_top24', 'dify_hybrid_rerank', 'Dify top-24: гибрид + реранк'),
    ('fastgpt', 'fastgpt_vector', 'FastGPT: вектор'),
    ('fastgpt', 'fastgpt_hybrid', 'FastGPT: гибрид'),
    ('anythingllm', 'anythingllm_default', 'AnythingLLM: top-4'),
    ('anythingllm', 'anythingllm_top8', 'AnythingLLM: top-8'),
    ('domain', 'hybrid_rerank', 'Прототип: чанкеры + гибрид + реранк'),
    ('domain', 'full', 'Полный прототип (parent-expansion)'),
)


def truncate(contexts: list[str], budget: int) -> list[str]:
    """Берёт контексты по порядку, пока не исчерпан бюджет токенов; последний обрезается."""
    encoding = get_encoding()
    result = []
    left = budget
    for text in contexts:
        tokens = encoding.encode(text, disallowed_special=())
        if len(tokens) >= left:
            result.append(encoding.decode(tokens[:left]))
            break
        result.append(text)
        left -= len(tokens)
    return result


def main() -> None:
    """Считает evidence recall по бюджетам и пишет CSV и markdown."""
    parser = argparse.ArgumentParser(prog='python -m benchmarks.budget_recall')
    parser.add_argument('--out-dir', type=Path, default=OUT_DIR)
    out_dir: Path = parser.parse_args().out_dir
    samples = {s.id: s for s in load_samples()}
    values: dict[tuple[str, int, str], list[float]] = defaultdict(list)
    systems = [x for x in SYSTEMS if (RAW_DIR / f'{x[0]}.jsonl').exists()]
    for run, config, label in systems:
        for record in _read_jsonl(RAW_DIR / f'{run}.jsonl'):
            sample = samples.get(record['id'])
            if sample is None:
                continue
            contexts = [c['content'] for c in record['contexts'][config]]
            for budget in BUDGETS:
                cut = truncate(contexts, budget)
                recall = score_sample(sample, cut, [''] * len(cut))['evidence_recall']
                for domain in (sample.domain, 'all'):
                    values[(label, budget, domain)].append(recall)
    rows = []
    lines = [
        '# Evidence recall при равном бюджете контекста',
        '',
        f'Вопросов: {len(samples)}. Контексты обрезаны до N токенов (cl100k) в порядке '
        'ранжирования. Среднее [95% bootstrap CI].',
        '',
    ]
    for domain in ('all', *DOMAINS):
        lines += [
            f'## {domain}',
            '',
            '| Система | ' + ' | '.join(f'{b} ток.' for b in BUDGETS) + ' |',
            '|---' * (len(BUDGETS) + 1) + '|',
        ]
        for _, _, label in systems:
            cells = []
            for budget in BUDGETS:
                mean, low, high = bootstrap_ci(values[(label, budget, domain)])
                rows.append(
                    [label, budget, domain, len(values[(label, budget, domain)]), mean, low, high]
                )
                cells.append(f'{mean:.3f} [{low:.2f}–{high:.2f}]')
            lines.append(f'| {label} | ' + ' | '.join(cells) + ' |')
        lines.append('')
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / 'budget_recall.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['system', 'budget_tokens', 'domain', 'n', 'mean', 'ci_low', 'ci_high'])
        writer.writerows(rows)
    report = '\n'.join(lines)
    (out_dir / 'budget_recall.md').write_text(report, encoding='utf-8')
    print(report)
    print(json.dumps({'questions': len(samples)}))


if __name__ == '__main__':
    main()
