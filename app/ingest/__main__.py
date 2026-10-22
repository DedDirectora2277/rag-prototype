"""CLI: `python -m app.ingest <файлы или каталоги> [--doc-type T] [--force]`."""

import argparse
import asyncio
import logging
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from openai import AsyncOpenAI

from app.config import get_settings
from app.db.client import create_pool, init_db
from app.ingest.parsers import UnsupportedFormatError, is_supported
from app.ingest.pipeline import ingest_path
from app.ingest.router import DOC_TYPES, DocType
from app.retrieval.embedder import Embedder

logger = logging.getLogger('app.ingest')


def iter_files(paths: list[Path]) -> Iterator[Path]:
    """Обходит файлы и каталоги, пропуская скрытые и неподдерживаемые файлы.

    Args:
        paths: Файлы и каталоги.

    Yields:
        Поддерживаемые файлы в детерминированном порядке.
    """
    for path in paths:
        if path.is_file():
            yield path
            continue
        for file in sorted(path.rglob('*')):
            hidden = any(part.startswith('.') for part in file.relative_to(path).parts)
            if file.is_file() and not hidden and is_supported(file.name):
                yield file


async def run(paths: list[Path], doc_type: DocType | None, force: bool) -> int:
    """Загружает файлы последовательно и печатает сводку.

    Args:
        paths: Файлы и каталоги.
        doc_type: Принудительный домен документов.
        force: Перезаписать неизменившиеся документы.

    Returns:
        Код возврата: 0 — без ошибок, 1 — были ошибки.
    """
    settings = get_settings()
    pool = await create_pool(settings)
    llm = AsyncOpenAI(base_url=f'{settings.litellm_url}/v1', api_key=settings.litellm_api_key)
    embedder = Embedder.from_settings(llm, settings)
    stats: Counter[str] = Counter()
    try:
        await init_db(pool, settings.embed_dim)
        for file in iter_files(paths):
            try:
                result = await ingest_path(
                    pool, embedder, settings, file, doc_type=doc_type, force=force
                )
            except (UnsupportedFormatError, OSError, ValueError) as exc:
                logger.error('%s: %s', file, exc)
                stats['errors'] += 1
                continue
            stats[result.status] += 1
            stats['chunks'] += result.chunks
    finally:
        await pool.close()
        await llm.close()
    logger.info('итого: %s', dict(stats))
    return 1 if stats['errors'] else 0


def main() -> None:
    """Точка входа CLI."""
    parser = argparse.ArgumentParser(prog='python -m app.ingest', description=__doc__)
    parser.add_argument('paths', nargs='+', type=Path, help='файлы или каталоги')
    parser.add_argument('--doc-type', choices=DOC_TYPES, help='домен (по умолчанию — авто)')
    parser.add_argument('--force', action='store_true', help='перезаписать без изменений')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    sys.exit(asyncio.run(run(args.paths, args.doc_type, args.force)))


if __name__ == '__main__':
    main()
