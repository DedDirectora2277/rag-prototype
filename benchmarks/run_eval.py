"""Прогон нашей системы по датасету: `python -m benchmarks.run_eval --tag domain`.

База, в которую загружен корпус, задаётся `RAG_DATABASE_DSN`: для режима `naive` корпус
грузится в отдельную базу (`RAG_CHUNKER_MODE=naive python -m app.ingest ...`).

Дорогие шаги считаются один раз на вопрос и переиспользуются конфигурациями ablation:
векторный и гибридный поиск — два SQL-запроса, реранк гибридных кандидатов — один вызов.
Конфигурации (все отдают `rerank_top_n` контекстов):
- `vector` — только векторный поиск;
- `hybrid` — вектор + FTS через RRF;
- `hybrid_rerank` — + переранжирование cross-encoder;
- `full` — + parent-expansion (наша система целиком).

Ответы по контекстам генерируются моделью `chat` для конфигураций из `--generate`.
Всё пишется построчно в `benchmarks/results/raw/<tag>*.jsonl`: прерванный прогон
продолжается с места остановки. Метрики без LLM → `benchmarks/results/<tag>-retrieval.md`.
"""

import argparse
import asyncio
import csv
import json
import logging
import sys
import time
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI, RateLimitError

from app.config import Settings, get_settings
from app.db.client import create_pool
from app.db.queries import SearchHit, hybrid_search
from app.generation import generate
from app.retrieval.embedder import Embedder
from app.retrieval.hybrid import RetrievedChunk, Retriever
from app.retrieval.reranker import Reranker
from benchmarks.dataset import DATASETS_DIR, DOMAINS, ROOT, Sample, read_samples
from benchmarks.metrics import bootstrap_ci, score_sample

logger = logging.getLogger('benchmarks.eval')

RESULTS_DIR = ROOT / 'results'
RAW_DIR = RESULTS_DIR / 'raw'
CONFIGS = ('vector', 'hybrid', 'hybrid_rerank', 'full')
METRICS = ('evidence_recall', 'hit', 'mrr', 'ap', 'precision', 'doc_recall')
GENERATION_CONCURRENCY = 3
RATE_LIMIT_RETRIES = 6
RATE_LIMIT_BACKOFF_S = 30.0


def load_samples(limit_per_domain: int | None = None) -> list[Sample]:
    """Читает вопросы всех доменов.

    Args:
        limit_per_domain: Взять первые N вопросов каждого домена (для пробного прогона).

    Returns:
        Вопросы.
    """
    samples = []
    for domain in DOMAINS:
        items = read_samples(DATASETS_DIR / f'{domain}.jsonl')
        samples += items[:limit_per_domain] if limit_per_domain else items
    return samples


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def _done_ids(path: Path) -> set[str]:
    return {r['id'] for r in _read_jsonl(path)}


def _context_json(ctx: RetrievedChunk) -> dict[str, Any]:
    data = asdict(ctx)
    data.pop('metadata')
    return data


async def retrieve_all(
    sample: Sample,
    retriever: Retriever,
    embedder: Embedder,
    reranker: Reranker,
    cfg: Settings,
    configs: Sequence[str] = CONFIGS,
) -> dict[str, list[RetrievedChunk]]:
    """Контексты всех конфигураций ablation для одного вопроса.

    Args:
        sample: Вопрос.
        retriever: Retriever (нужна сборка контекстов с parent-expansion).
        embedder: Эмбеддер запросов.
        reranker: Реранкер.
        cfg: Настройки (top-k, RRF).
        configs: Какие конфигурации считать; без `hybrid_rerank`/`full` реранк не вызывается.

    Returns:
        Конфигурация → контексты.
    """
    pool = retriever._pool
    embedding = await embedder.embed_query(sample.question)

    async def search(fts: bool) -> list[SearchHit]:
        return await hybrid_search(
            pool,
            embedding=embedding,
            query=sample.question,
            top_n=cfg.hybrid_top_n,
            vector_top_n=cfg.vector_top_n,
            fts_top_n=cfg.fts_top_n if fts else 0,
            rrf_k=cfg.rrf_k,
        )

    vec_hits = await search(fts=False)
    hyb_hits = await search(fts=True)

    def plain(hits: list[SearchHit]) -> list[tuple[SearchHit, float | None]]:
        return [(h, None) for h in hits]

    build = retriever._build_contexts
    top = cfg.rerank_top_n
    result = {
        'vector': await build(plain(vec_hits), top, False),
        'hybrid': await build(plain(hyb_hits), top, False),
    }
    if {'hybrid_rerank', 'full'} & set(configs):
        ranked = await reranker.rerank(sample.question, [h.content for h in hyb_hits])
        if ranked is None:
            raise RuntimeError('реранкер недоступен: конфигурации с реранком будут некорректны')
        reranked: list[tuple[SearchHit, float | None]] = [
            (hyb_hits[i], score) for i, score in ranked
        ]
        result['hybrid_rerank'] = await build(reranked, top, False)
        result['full'] = await build(reranked, top, True)
    return {k: v for k, v in result.items() if k in configs}


async def run_retrieval(
    samples: list[Sample], raw_path: Path, settings: Settings, configs: Sequence[str] = CONFIGS
) -> None:
    """Retrieval всех конфигураций по вопросам, которых ещё нет в `raw_path`.

    Args:
        samples: Вопросы.
        raw_path: Файл с сырыми результатами (дописывается).
        settings: Настройки.
        configs: Конфигурации ablation.
    """
    todo = [s for s in samples if s.id not in _done_ids(raw_path)]
    logger.info('retrieval: %s вопросов (%s уже готово)', len(todo), len(samples) - len(todo))
    if not todo:
        return
    pool = await create_pool(settings)
    llm = AsyncOpenAI(base_url=f'{settings.litellm_url}/v1', api_key=settings.litellm_api_key)
    http = Reranker.make_client(settings)
    embedder = Embedder.from_settings(llm, settings)
    reranker = Reranker(http, settings.rerank_model)
    retriever = Retriever(pool, embedder, reranker, settings)
    started = time.monotonic()
    try:
        for n, sample in enumerate(todo, start=1):
            contexts = await retrieve_all(sample, retriever, embedder, reranker, settings, configs)
            record = {
                'id': sample.id,
                'domain': sample.domain,
                'contexts': {k: [_context_json(c) for c in v] for k, v in contexts.items()},
            }
            with raw_path.open('a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
            elapsed = time.monotonic() - started
            logger.info(
                '[%s/%s] %s, %.0f с/вопрос, осталось ~%.0f мин',
                n,
                len(todo),
                sample.id,
                elapsed / n,
                elapsed / n * (len(todo) - n) / 60,
            )
    finally:
        await pool.close()
        await http.aclose()
        await llm.close()


async def run_generation(
    samples: list[Sample], raw_path: Path, config: str, settings: Settings
) -> None:
    """Генерирует ответы по контекстам конфигурации `config`.

    Args:
        samples: Вопросы.
        raw_path: Файл с контекстами.
        config: Конфигурация ablation.
        settings: Настройки (модель `chat`).
    """
    answers_path = raw_path.with_name(f'{raw_path.stem}-answers-{config}.jsonl')
    done = _done_ids(answers_path)
    raw = {r['id']: r for r in _read_jsonl(raw_path)}
    todo = [s for s in samples if s.id in raw and s.id not in done]
    logger.info('генерация %s: %s вопросов', config, len(todo))
    llm = AsyncOpenAI(base_url=f'{settings.litellm_url}/v1', api_key=settings.litellm_api_key)
    semaphore = asyncio.Semaphore(GENERATION_CONCURRENCY)

    async def one(sample: Sample) -> None:
        contexts = [RetrievedChunk(metadata={}, **c) for c in raw[sample.id]['contexts'][config]]
        async with semaphore:
            for attempt in range(1, RATE_LIMIT_RETRIES + 1):
                try:
                    result = await generate(llm, settings.chat_model, sample.question, contexts)
                    break
                except RateLimitError:
                    if attempt == RATE_LIMIT_RETRIES:
                        raise
                    await asyncio.sleep(RATE_LIMIT_BACKOFF_S)
        with answers_path.open('a', encoding='utf-8') as f:
            record = {
                'id': sample.id,
                'answer': result.text,
                'finish_reason': result.finish_reason,
            }
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    try:
        await asyncio.gather(*(one(s) for s in todo))
    finally:
        await llm.close()


def _write_csv(path: Path, header: list[str], rows: list[list[Any]]) -> None:
    with path.open('w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def score(samples: list[Sample], raw_path: Path, out_dir: Path = RESULTS_DIR) -> str:
    """Считает метрики без LLM по сырым результатам.

    Кроме markdown пишет два CSV для визуализации (pandas/Excel), оба в «длинном» формате:
    `<tag>-scores.csv` — значение метрики по каждому вопросу
    (`run, config, domain, source, language, id, metric, value`) и `<tag>-summary.csv` —
    среднее и 95% bootstrap CI (`run, config, domain, metric, n, mean, ci_low, ci_high`).

    Args:
        samples: Вопросы (метрики считаются только по ним).
        raw_path: Файл с контекстами.
        out_dir: Каталог для CSV.

    Returns:
        Таблица markdown: конфигурация × домен × метрика (среднее [95% CI]).
    """
    by_id = {s.id: s for s in samples}
    raw = [json.loads(line) for line in raw_path.read_text(encoding='utf-8').splitlines()]
    values: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    run_name = raw_path.stem
    rows = []
    for record in raw:
        sample = by_id.get(record['id'])
        if sample is None:
            continue
        for config, contexts in record['contexts'].items():
            scores = score_sample(
                sample, [c['content'] for c in contexts], [c['source'] for c in contexts]
            )
            for metric, value in scores.items():
                values[(config, sample.domain, metric)].append(value)
                values[(config, 'all', metric)].append(value)
                rows.append(
                    [
                        run_name,
                        config,
                        sample.domain,
                        sample.metadata.get('source', ''),
                        sample.metadata.get('language', ''),
                        sample.id,
                        metric,
                        value,
                    ]
                )
    _write_csv(
        out_dir / f'{run_name}-scores.csv',
        ['run', 'config', 'domain', 'source', 'language', 'id', 'metric', 'value'],
        rows,
    )
    summary = []
    for (config, domain, metric), vals in sorted(values.items()):
        mean, low, high = bootstrap_ci(vals)
        summary.append([run_name, config, domain, metric, len(vals), mean, low, high])
    _write_csv(
        out_dir / f'{run_name}-summary.csv',
        ['run', 'config', 'domain', 'metric', 'n', 'mean', 'ci_low', 'ci_high'],
        summary,
    )

    lines = [
        f'# Retrieval без LLM: `{raw_path.stem}`',
        '',
        'Среднее [95% bootstrap CI]. evidence_recall — доля эталонных фрагментов в top-k, '
        'hit — найден хотя бы один, mrr — 1/ранг первого релевантного контекста, '
        'ap — average precision (аналог Context Precision), precision — доля релевантных '
        'контекстов, doc_recall — доля эталонных документов среди источников.',
        '',
    ]
    present = {k[0] for k in values}
    configs = [c for c in CONFIGS if c in present] + sorted(present - set(CONFIGS))
    for domain in (*DOMAINS, 'all'):
        n = len(values.get((configs[0], domain, 'hit'), [])) if configs else 0
        lines += [f'## {domain} (n={n})', '', '| Конфигурация | ' + ' | '.join(METRICS) + ' |']
        lines.append('|---' * (len(METRICS) + 1) + '|')
        for config in configs:
            cells = []
            for metric in METRICS:
                mean, low, high = bootstrap_ci(values[(config, domain, metric)])
                cells.append(f'{mean:.3f} [{low:.2f}–{high:.2f}]')
            lines.append(f'| {config} | ' + ' | '.join(cells) + ' |')
        lines.append('')
    return '\n'.join(lines)


async def run(args: argparse.Namespace) -> int:
    """Выполняет шаги прогона.

    Args:
        args: Аргументы CLI.

    Returns:
        Код возврата.
    """
    settings = get_settings()
    samples = load_samples(args.limit_per_domain)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = RAW_DIR / f'{args.tag}.jsonl'
    if not args.score_only:
        await run_retrieval(samples, raw_path, settings, args.configs)
        for config in args.generate:
            await run_generation(samples, raw_path, config, settings)
    report = score(samples, raw_path)
    out = RESULTS_DIR / f'{args.tag}-retrieval.md'
    out.write_text(report, encoding='utf-8')
    logger.info('метрики → %s', out)
    print(report)
    return 0


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(prog='python -m benchmarks.run_eval')
    parser.add_argument('--tag', required=True, help='имя прогона (файлы results/raw/<tag>*)')
    parser.add_argument(
        '--configs', nargs='+', default=list(CONFIGS), choices=CONFIGS, help='конфигурации ablation'
    )
    parser.add_argument(
        '--generate',
        nargs='*',
        default=['full'],
        choices=CONFIGS,
        help='для каких конфигураций генерировать ответы',
    )
    parser.add_argument('--limit-per-domain', type=int, help='пробный прогон на N вопросах домена')
    parser.add_argument('--score-only', action='store_true', help='только пересчитать метрики')
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s'
    )
    for noisy in ('httpx', 'httpx2', 'openai'):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    sys.exit(asyncio.run(run(args)))


if __name__ == '__main__':
    main()
