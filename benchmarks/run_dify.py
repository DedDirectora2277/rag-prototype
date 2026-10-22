"""Прогон Dify по датасету: `python -m benchmarks.run_dify {ingest,eval} --dataset-id ID --key KEY`.

`ingest` загружает корпус в датасет Dify (разбиение Dify по умолчанию, режим `automatic`),
`eval` берёт контексты через Knowledge API в двух конфигурациях и пишет их в формате
`benchmarks.run_eval` (`results/raw/dify.jsonl`), генерирует ответы общим генератором
и считает те же метрики без LLM:
- `dify_vector` — векторный поиск top-8 (настройка датасета по умолчанию);
- `dify_hybrid_rerank` — гибридный поиск + тот же cross-encoder `rerank`, top-8.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from app.config import get_settings
from benchmarks.adapters.dify import DifyConfig, DifyKnowledge
from benchmarks.dataset import CORPUS_DIR
from benchmarks.run_eval import RAW_DIR, RESULTS_DIR, _done_ids, load_samples, run_generation, score

logger = logging.getLogger('benchmarks.dify')

TOP_K = 8
RERANK = {
    'reranking_provider_name': 'langgenius/openai_api_compatible/openai_api_compatible',
    'reranking_model_name': 'rerank',
}
CONFIGS: dict[str, dict[str, Any]] = {
    'dify_vector': {
        'search_method': 'semantic_search',
        'reranking_enable': False,
        'top_k': TOP_K,
        'score_threshold_enabled': False,
    },
    'dify_hybrid_rerank': {
        'search_method': 'hybrid_search',
        'reranking_enable': True,
        'reranking_mode': 'reranking_model',
        'reranking_model': RERANK,
        'top_k': TOP_K,
        'score_threshold_enabled': False,
    },
}
PROCESS = {'indexing_technique': 'high_quality', 'process_rule': {'mode': 'automatic'}}
MANIFEST = RAW_DIR / 'dify-uploads.jsonl'


async def ingest(client: DifyKnowledge, dataset_id: str) -> None:
    """Загружает корпус (имя документа — путь относительно corpus/), ждёт индексации."""
    done = _done_ids(MANIFEST)
    files = sorted(p for p in CORPUS_DIR.rglob('*') if p.is_file() and not p.name.startswith('.'))
    batches = []
    for path in files:
        rel = str(path.relative_to(CORPUS_DIR))
        if rel in done:
            continue
        name = rel.replace('/', '__')
        batch = await client.upload(dataset_id, path.read_bytes(), name, PROCESS)
        batches.append(batch)
        with MANIFEST.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'id': rel, 'batch': batch}) + '\n')
        logger.info('загружен %s', rel)
    all_batches = [json.loads(line)['batch'] for line in MANIFEST.read_text().splitlines()]
    await client.wait_indexed(dataset_id, all_batches)


def _source(record: dict[str, Any]) -> str:
    name = str(record['segment']['document']['name'])
    name = name.removesuffix('.txt') if name.count('.') > 1 else name
    return name.replace('__', '/')


async def retrieve(client: DifyKnowledge, dataset_id: str, raw_path: Path) -> None:
    """Контексты обеих конфигураций по вопросам, которых ещё нет в `raw_path`."""
    samples = load_samples()
    done = _done_ids(raw_path)
    todo = [s for s in samples if s.id not in done]
    for n, sample in enumerate(todo, start=1):
        contexts = {}
        for config, model in CONFIGS.items():
            records = await client.retrieve(dataset_id, sample.question, model)
            contexts[config] = [
                {
                    'chunk_id': i,
                    'content': r['segment']['content'],
                    'chunk_type': 'dify_segment',
                    'source': _source(r),
                    'doc_type': '',
                    'title': None,
                    'score': float(r.get('score') or 0.0),
                    'rrf_score': 0.0,
                    'rerank_score': None,
                    'matched_chunk_ids': [],
                }
                for i, r in enumerate(records)
            ]
        record = {'id': sample.id, 'domain': sample.domain, 'contexts': contexts}
        with raw_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        logger.info('[%s/%s] %s', n, len(todo), sample.id)


async def run(args: argparse.Namespace) -> int:
    """Выполняет шаг `ingest` или `eval`."""
    client = DifyKnowledge(DifyConfig(), args.key)
    raw_path = RAW_DIR / 'dify.jsonl'
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if args.step == 'ingest':
            await ingest(client, args.dataset_id)
            return 0
        await retrieve(client, args.dataset_id, raw_path)
    finally:
        await client.close()
    samples = load_samples()
    settings = get_settings()
    for config in CONFIGS:
        await run_generation(samples, raw_path, config, settings)
    report = score(samples, raw_path)
    (RESULTS_DIR / 'dify-retrieval.md').write_text(report, encoding='utf-8')
    print(report)
    return 0


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(prog='python -m benchmarks.run_dify')
    parser.add_argument('step', choices=('ingest', 'eval'))
    parser.add_argument('--dataset-id', required=True)
    parser.add_argument('--key', required=True, help='API-ключ Knowledge API (dataset-...)')
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s'
    )
    logging.getLogger('httpx').setLevel(logging.WARNING)
    sys.exit(asyncio.run(run(args)))


if __name__ == '__main__':
    main()
