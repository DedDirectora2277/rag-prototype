"""Прогон FastGPT по датасету: `python -m benchmarks.run_fastgpt {setup,ingest,eval}`.

`setup` настраивает чистый инстанс (`docker compose up` из `competitors/fastgpt`, FastGPT 4.17,
порт 3000): системные модели `chat`/`embed`/`rerank` из LiteLLM, модели по умолчанию и датасет;
id датасета и моделей пишутся в `results/raw/fastgpt-instance.json`. `ingest` загружает корпус
(разбиение FastGPT по умолчанию: `chunk`, `chunkSettingMode=auto`) и ждёт индексации. `eval`
берёт контексты через `searchTest` в двух конфигурациях и пишет их в формате `benchmarks.run_eval`
(`results/raw/fastgpt.jsonl`), генерирует ответы общим генератором и считает метрики без LLM:
- `fastgpt_vector` — векторный поиск (режим узла поиска по умолчанию);
- `fastgpt_hybrid` — `mixedRecall` (вектор + полнотекстовый, RRF), без реранка.

Реранк FastGPT отправляет всю гибридную выдачу (~120 фрагментов) одним запросом с жёстким
таймаутом 30 с (`packages/service/core/ai/rerank`); общий cross-encoder стенда на GTX 1650 Ti
за это время не успевает, и FastGPT молча отдаёт выдачу без реранка. Поэтому конфигурации
с реранком нет: на этом железе она не отличалась бы от `fastgpt_hybrid`.

Выдача FastGPT ограничивается не числом фрагментов, а бюджетом токенов (`limit`, по умолчанию
5000). Порог `similarity` отключён (0), как и `score_threshold` у Dify.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from app.config import get_settings
from benchmarks.adapters import corpus_files, upload_name, upload_names
from benchmarks.adapters.fastgpt import SUPPORTED, FastGPTClient, FastGPTConfig
from benchmarks.dataset import CORPUS_DIR
from benchmarks.run_eval import RAW_DIR, RESULTS_DIR, _done_ids, load_samples, run_generation, score

logger = logging.getLogger('benchmarks.fastgpt')

LIMIT = 5000
INSTANCE = RAW_DIR / 'fastgpt-instance.json'
MANIFEST = RAW_DIR / 'fastgpt-uploads.jsonl'


def configs(limit: int = LIMIT) -> dict[str, dict[str, Any]]:
    """Параметры `searchTest` для обеих конфигураций."""
    base = {
        'limit': limit,
        'similarity': 0,
        'usingReRank': False,
        'datasetSearchUsingExtensionQuery': False,
    }
    return {
        'fastgpt_vector': {**base, 'searchMode': 'embedding'},
        'fastgpt_hybrid': {**base, 'searchMode': 'mixedRecall'},
    }


def _models(cfg: FastGPTConfig) -> list[dict[str, Any]]:
    url = cfg.litellm_url
    common = {'provider': 'Other', 'requestAuth': cfg.litellm_key, 'isActive': True}
    return [
        {
            **common,
            'type': 'llm',
            'model': 'chat',
            'name': 'chat',
            'requestUrl': f'{url}/chat/completions',
            'config': {'maxContext': 64000, 'maxResponse': 4096, 'quoteMaxToken': 60000},
        },
        {
            **common,
            'type': 'embedding',
            'model': 'embed',
            'name': 'embed',
            'requestUrl': f'{url}/embeddings',
            # Как у шаблонов OpenAI-эмбеддеров в FastGPT; bge-m3 принимает до 8192 токенов.
            'config': {'defaultToken': 512, 'maxToken': 8000, 'weight': 0},
        },
        {
            **common,
            'type': 'rerank',
            'model': 'rerank',
            'name': 'rerank',
            'requestUrl': f'{url}/rerank',
            'config': {'maxToken': 8192},
        },
    ]


async def setup(cfg: FastGPTConfig) -> None:
    """Настраивает инстанс FastGPT и создаёт датасет (см. docstring модуля)."""
    client = FastGPTClient(cfg)
    try:
        await client.login()
        ids = {}
        for model in _models(cfg):
            created = await client.call(
                'POST', '/admin/system/model/create', json={'modelData': model, 'channelIds': []}
            )
            ids[model['type']] = created['modelId']
        await client.call(
            'POST',
            '/admin/system/model/updateDefault',
            json={**ids, 'datasetTextLLMModelId': ids['llm']},
        )
        dataset_id = await client.call(
            'POST',
            '/core/dataset/create',
            json={
                'type': 'dataset',
                'name': cfg.dataset_name,
                'intro': '',
                'vectorModelId': ids['embedding'],
                'agentModelId': ids['llm'],
            },
        )
    finally:
        await client.close()
    INSTANCE.write_text(json.dumps({'dataset_id': dataset_id, 'models': ids}), encoding='utf-8')
    logger.info('датасет %s, модели %s', dataset_id, ids)


def fastgpt_name(rel: str) -> str:
    """Имя файла в FastGPT для пути корпуса (см. `upload_name`)."""
    return upload_name(rel, SUPPORTED)


def corpus_path(name: str) -> str:
    """Путь документа в корпусе по имени коллекции FastGPT (обратное к `fastgpt_name`)."""
    return upload_names(SUPPORTED).get(name, name)


async def ingest(client: FastGPTClient, dataset_id: str) -> None:
    """Загружает корпус (одна коллекция на файл), ждёт индексации."""
    done = _done_ids(MANIFEST)
    for path in corpus_files():
        rel = str(path.relative_to(CORPUS_DIR))
        if rel in done:
            continue
        try:
            collection = await client.upload(dataset_id, path.read_bytes(), fastgpt_name(rel))
        except RuntimeError as e:
            logger.error('не загружен %s: %s', rel, e)
            continue
        with MANIFEST.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'id': rel, 'collection': collection}) + '\n')
        logger.info('загружен %s', rel)
    await client.wait_trained(dataset_id)


def _score(item: dict[str, Any]) -> float:
    # `score` — список оценок по типам поиска (embedding/fullText/reRank/rrf), первая — итоговая.
    scores = item.get('score') or []
    return float(scores[0]['value']) if scores else 0.0


async def retrieve(
    client: FastGPTClient, dataset_id: str, raw_path: Path, params: dict[str, dict[str, Any]]
) -> None:
    """Контексты обеих конфигураций по вопросам, которых ещё нет в `raw_path`."""
    samples = load_samples()
    done = _done_ids(raw_path)
    todo = [s for s in samples if s.id not in done]
    for n, sample in enumerate(todo, start=1):
        contexts: dict[str, list[dict[str, Any]]] = {}
        for config, search in params.items():
            items = await client.search(dataset_id, sample.question, search)
            contexts[config] = [
                {
                    'chunk_id': i,
                    'content': '\n'.join(x for x in (item.get('q'), item.get('a')) if x),
                    'chunk_type': 'fastgpt_chunk',
                    'source': corpus_path(str(item.get('sourceName', ''))),
                    'doc_type': '',
                    'title': None,
                    'score': _score(item),
                    'rrf_score': 0.0,
                    'rerank_score': None,
                    'matched_chunk_ids': [],
                }
                for i, item in enumerate(items)
            ]
        record = {'id': sample.id, 'domain': sample.domain, 'contexts': contexts}
        with raw_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        logger.info('[%s/%s] %s', n, len(todo), sample.id)


async def run(args: argparse.Namespace) -> int:
    """Выполняет шаг `setup`, `ingest` или `eval`."""
    cfg = FastGPTConfig()
    if args.step == 'setup':
        await setup(cfg)
        return 0
    instance = json.loads(INSTANCE.read_text(encoding='utf-8'))
    dataset_id = instance['dataset_id']
    params = configs(args.limit)
    client = FastGPTClient(cfg)
    raw_path = RAW_DIR / f'{args.tag}.jsonl'
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    try:
        await client.login()
        if args.step == 'ingest':
            await ingest(client, dataset_id)
            return 0
        await retrieve(client, dataset_id, raw_path, params)
    finally:
        await client.close()
    samples = load_samples()
    if not args.skip_generation:
        settings = get_settings()
        for config in params:
            await run_generation(samples, raw_path, config, settings)
    out_dir = Path(args.out_dir) if args.out_dir else RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    report = score(samples, raw_path, out_dir)
    (out_dir / f'{args.tag}-retrieval.md').write_text(report, encoding='utf-8')
    print(report)
    return 0


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(prog='python -m benchmarks.run_fastgpt')
    parser.add_argument('step', choices=('setup', 'ingest', 'eval'))
    parser.add_argument('--tag', default='fastgpt', help='имя прогона (results/raw/<tag>.jsonl)')
    parser.add_argument('--limit', type=int, default=LIMIT, help='бюджет выдачи в токенах')
    parser.add_argument('--out-dir', help='каталог для метрик (по умолчанию results/)')
    parser.add_argument('--skip-generation', action='store_true', help='только retrieval')
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s'
    )
    logging.getLogger('httpx').setLevel(logging.WARNING)
    sys.exit(asyncio.run(run(args)))


if __name__ == '__main__':
    main()
