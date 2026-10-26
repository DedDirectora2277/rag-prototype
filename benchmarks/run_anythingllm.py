"""Прогон AnythingLLM по датасету: `python -m benchmarks.run_anythingllm {setup,ingest,eval}`.

`setup` настраивает чистый инстанс (`docker compose up` из `competitors/anythingllm`,
AnythingLLM 1.18, порт 3001): ключ Developer API и workspace; ключ и slug пишутся в
`results/raw/anythingllm-instance.json`. `ingest` загружает корпус и добавляет документы
в workspace (нарезка AnythingLLM по умолчанию: 1000 символов, перекрытие 20). `eval` берёт
контексты через `vector-search` в двух конфигурациях и пишет их в формате `benchmarks.run_eval`
(`results/raw/anythingllm.jsonl`), генерирует ответы общим генератором и считает метрики без LLM:
- `anythingllm_default` — настройки workspace по умолчанию (top-N и порог сходства);
- `anythingllm_top8` — top-8 без порога, как у Dify.

Гибридного поиска в AnythingLLM нет, а его реранкер — встроенная локальная модель, а не
общий cross-encoder стенда, поэтому реранк не используется.
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
from benchmarks.adapters.anythingllm import (
    SUPPORTED,
    AnythingLLMClient,
    AnythingLLMConfig,
    generate_api_key,
)
from benchmarks.dataset import CORPUS_DIR
from benchmarks.run_eval import RAW_DIR, RESULTS_DIR, _done_ids, load_samples, run_generation, score

logger = logging.getLogger('benchmarks.anythingllm')

INSTANCE = RAW_DIR / 'anythingllm-instance.json'
MANIFEST = RAW_DIR / 'anythingllm-uploads.jsonl'
EMBED_BATCH = 8


async def setup(cfg: AnythingLLMConfig) -> None:
    """Создаёт ключ API и workspace (см. docstring модуля)."""
    key = await generate_api_key(cfg)
    client = AnythingLLMClient(cfg, key)
    try:
        created = await client.call('POST', '/workspace/new', json={'name': cfg.workspace_name})
    finally:
        await client.close()
    workspace = created['workspace']
    INSTANCE.write_text(json.dumps({'key': key, 'slug': workspace['slug']}), encoding='utf-8')
    logger.info(
        'workspace %s: topN=%s, similarityThreshold=%s',
        workspace['slug'],
        workspace.get('topN'),
        workspace.get('similarityThreshold'),
    )


def anythingllm_name(rel: str) -> str:
    """Имя файла в AnythingLLM для пути корпуса (см. `upload_name`)."""
    return upload_name(rel, SUPPORTED)


def corpus_path(name: str) -> str:
    """Путь документа в корпусе по заголовку документа AnythingLLM."""
    return upload_names(SUPPORTED).get(name, name)


async def ingest(client: AnythingLLMClient, slug: str) -> None:
    """Загружает корпус и добавляет его в workspace пачками по `EMBED_BATCH` документов."""
    done = _done_ids(MANIFEST)
    todo = [p for p in corpus_files() if str(p.relative_to(CORPUS_DIR)) not in done]
    for i in range(0, len(todo), EMBED_BATCH):
        batch = []
        for path in todo[i : i + EMBED_BATCH]:
            rel = str(path.relative_to(CORPUS_DIR))
            try:
                location = await client.upload(path.read_bytes(), anythingllm_name(rel))
            except RuntimeError as e:
                logger.error('не загружен %s: %s', rel, e)
                continue
            batch.append((rel, location))
        await client.embed(slug, [location for _, location in batch])
        with MANIFEST.open('a', encoding='utf-8') as f:
            for rel, location in batch:
                f.write(json.dumps({'id': rel, 'location': location}) + '\n')
        logger.info('в workspace: %s из %s', i + len(batch), len(todo))


def configs(workspace: dict[str, Any]) -> dict[str, tuple[int, float]]:
    """(top-N, порог сходства) обеих конфигураций."""
    return {
        'anythingllm_default': (
            int(workspace.get('topN') or 4),
            float(workspace.get('similarityThreshold') or 0.25),
        ),
        'anythingllm_top8': (8, 0.0),
    }


async def retrieve(
    client: AnythingLLMClient, slug: str, raw_path: Path, params: dict[str, tuple[int, float]]
) -> None:
    """Контексты обеих конфигураций по вопросам, которых ещё нет в `raw_path`."""
    samples = load_samples()
    done = _done_ids(raw_path)
    todo = [s for s in samples if s.id not in done]
    for n, sample in enumerate(todo, start=1):
        contexts: dict[str, list[dict[str, Any]]] = {}
        for config, (top_n, threshold) in params.items():
            items = await client.search(slug, sample.question, top_n, threshold)
            contexts[config] = [
                {
                    'chunk_id': i,
                    'content': item['text'],
                    'chunk_type': 'anythingllm_chunk',
                    'source': corpus_path(str(item['metadata'].get('title', ''))),
                    'doc_type': '',
                    'title': None,
                    'score': float(item.get('score') or 0.0),
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
    cfg = AnythingLLMConfig()
    if args.step == 'setup':
        await setup(cfg)
        return 0
    instance = json.loads(INSTANCE.read_text(encoding='utf-8'))
    slug = instance['slug']
    client = AnythingLLMClient(cfg, instance['key'])
    raw_path = RAW_DIR / f'{args.tag}.jsonl'
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if args.step == 'ingest':
            await ingest(client, slug)
            return 0
        workspace = (await client.call('GET', f'/workspace/{slug}'))['workspace'][0]
        params = configs(workspace)
        logger.info('конфигурации: %s', params)
        await retrieve(client, slug, raw_path, params)
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
    parser = argparse.ArgumentParser(prog='python -m benchmarks.run_anythingllm')
    parser.add_argument('step', choices=('setup', 'ingest', 'eval'))
    parser.add_argument('--tag', default='anythingllm', help='имя прогона (raw/<tag>.jsonl)')
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
