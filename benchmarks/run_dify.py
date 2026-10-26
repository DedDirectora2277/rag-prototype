"""Прогон Dify по датасету: `python -m benchmarks.run_dify {setup,ingest,retry,eval}`.

`setup` настраивает чистый инстанс (`docker compose up` из репозитория Dify 1.17.1, порт 8090):
администратор, плагин OpenAI-API-compatible, модели `chat`/`embed`/`rerank` из LiteLLM
по умолчанию, ключ Knowledge API и датасет; ключ и id пишутся в
`results/raw/dify-instance.json`, их читают остальные шаги. `ingest` загружает корпус
в датасет Dify (разбиение Dify по умолчанию, режим `automatic`),
`eval` берёт контексты через Knowledge API в двух конфигурациях и пишет их в формате
`benchmarks.run_eval` (`results/raw/dify.jsonl`), генерирует ответы общим генератором
и считает те же метрики без LLM:
- `dify_vector` — векторный поиск top-8 (настройка датасета по умолчанию);
- `dify_hybrid_rerank` — гибридный поиск + тот же cross-encoder `rerank`, top-8.
"""

import argparse
import asyncio
import functools
import json
import logging
import sys
from pathlib import Path
from typing import Any

from app.config import get_settings
from benchmarks.adapters.dify import (
    PROVIDER,
    SUPPORTED,
    DifyConfig,
    DifyConsole,
    DifyKnowledge,
)
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
PLUGIN = (
    'langgenius/openai_api_compatible:0.0.68@'
    'ba61c5eccb814be7364117c0bec3710a51e09b20f31e37243e747a00f9377969'
)
INSTANCE = RAW_DIR / 'dify-instance.json'
RETRY_GROUP = 3
RETRY_ATTEMPTS = 3
PROCESS = {'indexing_technique': 'high_quality', 'process_rule': {'mode': 'automatic'}}
MANIFEST = RAW_DIR / 'dify-uploads.jsonl'


def _models(cfg: DifyConfig) -> list[tuple[str, str, dict[str, str]]]:
    base = {'endpoint_url': cfg.litellm_url, 'api_key': cfg.litellm_key}
    chat = {
        **base,
        'mode': 'chat',
        'context_size': '64000',
        'max_tokens_to_sample': '4096',
        'function_calling_type': 'no_call',
        'stream_function_calling': 'not_supported',
        'vision_support': 'no_support',
        'structured_output_support': 'not_supported',
    }
    return [
        ('chat', 'llm', chat),
        ('embed', 'text-embedding', {**base, 'context_size': '8192', 'max_chunks': '64'}),
        ('rerank', 'rerank', {**base, 'context_size': '8192'}),
    ]


async def setup(cfg: DifyConfig) -> None:
    """Настраивает инстанс Dify и создаёт датасет (см. docstring модуля)."""
    console = DifyConsole(cfg)
    try:
        await console.setup_and_login()
        task = await console.call(
            'POST',
            '/workspaces/current/plugin/install/marketplace',
            json={'plugin_unique_identifiers': [PLUGIN]},
        )
        while task.get('task_id'):
            status = await console.call(
                'GET', f'/workspaces/current/plugin/tasks/{task["task_id"]}'
            )
            if status['task']['status'] in ('success', 'failed'):
                logger.info('плагин: %s', status['task']['status'])
                break
            await asyncio.sleep(5)
        models = _models(cfg)
        for name, model_type, credentials in models:
            await console.call(
                'POST',
                f'/workspaces/current/model-providers/{PROVIDER}/models/credentials',
                json={
                    'model': name,
                    'model_type': model_type,
                    'credentials': credentials,
                    'name': name,
                },
            )
        await console.call(
            'POST',
            '/workspaces/current/default-model',
            json={
                'model_settings': [
                    {'model_type': t, 'provider': PROVIDER, 'model': n} for n, t, _ in models
                ]
            },
        )
        key = (await console.call('POST', '/datasets/api-keys'))['token']
    finally:
        await console.close()
    knowledge = DifyKnowledge(cfg, key)
    try:
        dataset = await knowledge.call(
            'POST',
            '/datasets',
            json={
                'name': cfg.dataset_name,
                'indexing_technique': 'high_quality',
                'permission': 'only_me',
                'embedding_model': 'embed',
                'embedding_model_provider': PROVIDER,
                'retrieval_model': CONFIGS['dify_vector'],
            },
        )
    finally:
        await knowledge.close()
    INSTANCE.write_text(json.dumps({'key': key, 'dataset_id': dataset['id']}), encoding='utf-8')
    logger.info('датасет %s, ключ сохранён в %s', dataset['id'], INSTANCE)


async def ingest(client: DifyKnowledge, dataset_id: str) -> None:
    """Загружает корпус (имя документа — путь относительно corpus/), ждёт индексации."""
    done = _done_ids(MANIFEST)
    batches = []
    for path in corpus_files():
        rel = str(path.relative_to(CORPUS_DIR))
        if rel in done:
            continue
        batch = await client.upload(dataset_id, path.read_bytes(), rel.replace('/', '__'), PROCESS)
        batches.append(batch)
        with MANIFEST.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'id': rel, 'batch': batch}) + '\n')
        logger.info('загружен %s', rel)
    all_batches = [json.loads(line)['batch'] for line in MANIFEST.read_text().splitlines()]
    await client.wait_indexed(dataset_id, all_batches)


async def failed_documents(client: DifyKnowledge, dataset_id: str) -> list[str]:
    """id документов датасета со статусом индексации `error`."""
    failed = []
    page = 1
    while True:
        data = await client.call(
            'GET', f'/datasets/{dataset_id}/documents', params={'page': page, 'limit': 100}
        )
        failed += [d['id'] for d in data['data'] if d['indexing_status'] == 'error']
        if not data.get('has_more'):
            return failed
        page += 1


async def retry_failed(cfg: DifyConfig, client: DifyKnowledge, dataset_id: str) -> None:
    """Переиндексирует упавшие документы группами по `RETRY_GROUP`, пока ошибок не останется.

    Под нагрузкой Dify исчерпывает пул соединений к своей БД (`QueuePool limit`), а запросы
    к эмбеддеру обрываются; повторная индексация небольшими группами проходит.
    """
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        failed = await failed_documents(client, dataset_id)
        logger.info('попытка %s: документов с ошибкой %s', attempt, len(failed))
        if not failed:
            return
        console = DifyConsole(cfg)
        try:
            await console.setup_and_login()
            for i in range(0, len(failed), RETRY_GROUP):
                group = failed[i : i + RETRY_GROUP]
                await console.call(
                    'POST', f'/datasets/{dataset_id}/retry', json={'document_ids': group}
                )
                while True:
                    await asyncio.sleep(10)
                    docs = await client.call(
                        'GET', f'/datasets/{dataset_id}/documents', params={'limit': 100}
                    )
                    page = {d['id']: d['indexing_status'] for d in docs['data']}
                    # Документы группы могут оказаться на других страницах — тогда ждём по всем.
                    states = {page.get(d, 'unknown') for d in group}
                    if not states & {'waiting', 'parsing', 'cleaning', 'splitting', 'indexing'}:
                        break
        finally:
            await console.close()
    raise RuntimeError('после повторов остались документы с ошибкой индексации')


def corpus_files() -> list[Path]:
    """Файлы корпуса для загрузки (без скрытых и lock-файлов Office `~$…`)."""
    return sorted(
        p for p in CORPUS_DIR.rglob('*') if p.is_file() and not p.name.startswith(('.', '~$'))
    )


def dify_name(rel: str) -> str:
    """Имя документа в Dify для пути корпуса: `/` → `__`, неподдерживаемым — суффикс `.txt`."""
    name = rel.replace('/', '__')
    return name if Path(name).suffix.lower() in SUPPORTED else f'{name}.txt'


@functools.cache
def _names() -> dict[str, str]:
    return {
        dify_name(str(p.relative_to(CORPUS_DIR))): str(p.relative_to(CORPUS_DIR))
        for p in corpus_files()
    }


def corpus_path(name: str) -> str:
    """Путь документа в корпусе по имени документа Dify (обратное к `dify_name`).

    Обратная замена `__` → `/` неоднозначна для имён вроде `__init__.py`, поэтому путь
    ищется среди файлов корпуса; эвристика — только для документов вне корпуса.
    """
    if name in _names():
        return _names()[name]
    base = name.removesuffix('.txt')
    if name.endswith('.txt') and Path(base).suffix.lower() in {'.py', '.rst'}:
        name = base
    return name.replace('__', '/')


def _source(record: dict[str, Any]) -> str:
    return corpus_path(str(record['segment']['document']['name']))


async def retrieve(
    client: DifyKnowledge, dataset_id: str, raw_path: Path, top_k: int = TOP_K
) -> None:
    """Контексты обеих конфигураций (с `top_k`) по вопросам, которых ещё нет в `raw_path`."""
    samples = load_samples()
    done = _done_ids(raw_path)
    todo = [s for s in samples if s.id not in done]
    for n, sample in enumerate(todo, start=1):
        contexts = {}
        for config, model in CONFIGS.items():
            records = await client.retrieve(dataset_id, sample.question, {**model, 'top_k': top_k})
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
    """Выполняет шаг `setup`, `ingest` или `eval`."""
    cfg = DifyConfig()
    if args.step == 'setup':
        await setup(cfg)
        return 0
    instance = json.loads(INSTANCE.read_text(encoding='utf-8'))
    dataset_id = args.dataset_id or instance['dataset_id']
    client = DifyKnowledge(cfg, args.key or instance['key'])
    raw_path = RAW_DIR / f'{args.tag}.jsonl'
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if args.step == 'ingest':
            await ingest(client, dataset_id)
            return 0
        if args.step == 'retry':
            await retry_failed(cfg, client, dataset_id)
            return 0
        await retrieve(client, dataset_id, raw_path, args.top_k)
    finally:
        await client.close()
    samples = load_samples()
    if not args.skip_generation:
        settings = get_settings()
        for config in CONFIGS:
            await run_generation(samples, raw_path, config, settings)
    out_dir = Path(args.out_dir) if args.out_dir else RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    report = score(samples, raw_path, out_dir)
    (out_dir / f'{args.tag}-retrieval.md').write_text(report, encoding='utf-8')
    print(report)
    return 0


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(prog='python -m benchmarks.run_dify')
    parser.add_argument('step', choices=('setup', 'ingest', 'retry', 'eval'))
    parser.add_argument('--dataset-id', help='по умолчанию — из results/raw/dify-instance.json')
    parser.add_argument('--key', help='ключ Knowledge API; по умолчанию — из dify-instance.json')
    parser.add_argument('--tag', default='dify', help='имя прогона (results/raw/<tag>.jsonl)')
    parser.add_argument('--top-k', type=int, default=TOP_K, help='число сегментов в выдаче')
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
