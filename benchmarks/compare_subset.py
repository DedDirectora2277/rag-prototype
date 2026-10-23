"""Сравнение систем на общем подмножестве вопросов: `python -m benchmarks.compare_subset`.

Dify проиндексировал не весь корпус: часть документов упала с ошибками его собственной
очереди индексации (исчерпание пула соединений к БД и утёкшие транзакции). Чтобы не штрафовать
Dify за это и не давать преимущества остальным, метрики всех систем пересчитываются на
вопросах, все эталонные документы которых есть в индексе Dify. Результаты, графики и список
отсутствующих документов — в `benchmarks/results/dify_subset/`.
"""

import asyncio
import json

from benchmarks import plots
from benchmarks.adapters.dify import DifyConfig, DifyKnowledge
from benchmarks.judge_answers import summarize
from benchmarks.run_dify import INSTANCE, corpus_path
from benchmarks.run_eval import RAW_DIR, RESULTS_DIR, load_samples, score

OUT_DIR = RESULTS_DIR / 'dify_subset'
RUNS = ('domain', 'naive', 'dify')
JUDGED = ('domain:full', 'naive:vector', 'dify:dify_vector', 'dify:dify_hybrid_rerank')


async def indexed_documents() -> tuple[set[str], set[str]]:
    """Пути документов корпуса: проиндексированные в Dify и все загруженные."""
    instance = json.loads(INSTANCE.read_text(encoding='utf-8'))
    client = DifyKnowledge(DifyConfig(), instance['key'])
    done, uploaded = set(), set()
    try:
        page = 1
        while True:
            data = await client.call(
                'GET',
                f'/datasets/{instance["dataset_id"]}/documents',
                params={'page': page, 'limit': 100},
            )
            for doc in data['data']:
                path = corpus_path(doc['name'])
                uploaded.add(path)
                if doc['indexing_status'] == 'completed':
                    done.add(path)
            if not data.get('has_more'):
                break
            page += 1
    finally:
        await client.close()
    return done, uploaded


def main() -> None:
    """Пересчитывает метрики на общем подмножестве и строит графики."""
    done, uploaded = asyncio.run(indexed_documents())
    samples = load_samples()
    subset = [s for s in samples if all(d in done for d in s.source_docs)]
    ids = {s.id for s in subset}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / 'coverage.json').write_text(
        json.dumps(
            {
                'indexed_documents': len(done),
                'uploaded_documents': len(uploaded),
                'missing_documents': sorted(uploaded - done),
                'questions_total': len(samples),
                'questions_in_subset': len(subset),
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding='utf-8',
    )
    print(f'Dify: проиндексировано {len(done)}/{len(uploaded)} документов')
    print(f'вопросов в общем подмножестве: {len(subset)}/{len(samples)}')
    for run in RUNS:
        raw = RAW_DIR / f'{run}.jsonl'
        if raw.exists():
            report = score(subset, raw, OUT_DIR)
            (OUT_DIR / f'{run}-retrieval.md').write_text(report, encoding='utf-8')
    judged = [t for t in JUDGED if (RAW_DIR / f'judge-{t.replace(":", "-")}.jsonl').exists()]
    print(summarize(judged, ids, OUT_DIR))
    plots.main(OUT_DIR)


if __name__ == '__main__':
    main()
