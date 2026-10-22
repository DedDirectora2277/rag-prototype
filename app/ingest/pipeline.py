"""Ingest: парсинг → выбор чанкера → эмбеддинги retrievable-чанков → запись в БД."""

import asyncio
import hashlib
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

from app.chunkers.base import flatten
from app.config import Settings
from app.db.client import (
    Pool,
    delete_document,
    get_document_by_source,
    insert_chunks,
    insert_document,
)
from app.ingest.parsers import parse_bytes
from app.ingest.router import DocType, chunk_document, detect_doc_type
from app.retrieval.embedder import Embedder

logger = logging.getLogger(__name__)

IngestStatus = Literal['created', 'updated', 'unchanged']


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Итог загрузки документа.

    Attributes:
        document_id: Идентификатор документа в БД.
        source: Источник документа.
        doc_type: Домен документа.
        status: `created`, `updated` (содержимое изменилось) или `unchanged`.
        chunks: Сколько чанков записано (вместе с parent).
        retrievable: Сколько из них участвует в поиске.
    """

    document_id: int
    source: str
    doc_type: str
    status: IngestStatus
    chunks: int = 0
    retrievable: int = 0


async def ingest_path(
    pool: Pool,
    embedder: Embedder,
    settings: Settings,
    path: Path,
    *,
    doc_type: DocType | None = None,
    force: bool = False,
) -> IngestResult:
    """Загружает файл с диска; источником документа служит путь как есть.

    Args:
        pool: Пул соединений.
        embedder: Эмбеддер.
        settings: Настройки (режим и размеры чанкинга).
        path: Путь к файлу.
        doc_type: Домен документа; `None` — определить автоматически.
        force: Перезаписать документ, даже если содержимое не изменилось.

    Returns:
        Итог загрузки.
    """
    return await ingest_bytes(
        pool,
        embedder,
        settings,
        await asyncio.to_thread(path.read_bytes),
        filename=path.name,
        source=path.as_posix(),
        doc_type=doc_type,
        force=force,
    )


async def ingest_bytes(
    pool: Pool,
    embedder: Embedder,
    settings: Settings,
    data: bytes,
    *,
    filename: str,
    source: str | None = None,
    doc_type: DocType | None = None,
    force: bool = False,
) -> IngestResult:
    """Загружает документ из памяти (например, из multipart-загрузки).

    Повторная загрузка того же `source` с тем же хешем содержимого ничего не
    делает; с другим хешем старая версия удаляется и записывается новая.
    Эмбеддинги считаются до транзакции, чтобы не держать её открытой.

    Args:
        pool: Пул соединений.
        embedder: Эмбеддер.
        settings: Настройки (режим и размеры чанкинга).
        data: Содержимое файла.
        filename: Имя файла (по расширению выбирается парсер).
        source: Источник документа; по умолчанию — `filename`.
        doc_type: Домен документа; `None` — определить автоматически.
        force: Перезаписать документ, даже если содержимое не изменилось.

    Returns:
        Итог загрузки.
    """
    source = source or filename
    content_hash = hashlib.sha256(data).hexdigest()
    existing = await get_document_by_source(pool, source)
    if existing is not None and existing.content_hash == content_hash and not force:
        return IngestResult(existing.id, source, existing.doc_type, 'unchanged')

    doc = parse_bytes(data, filename, source)
    doc_type = doc_type or detect_doc_type(doc)
    records = flatten(chunk_document(doc, doc_type, settings))
    if not records:
        logger.warning('%s: документ не дал ни одного чанка', source)

    retrievable = [i for i, record in enumerate(records) if record.is_retrievable]
    vectors = await embedder.embed([records[i].content for i in retrievable])
    for i, vector in zip(retrievable, vectors, strict=True):
        records[i] = replace(records[i], embedding=vector)

    async with pool.acquire() as conn, conn.transaction():
        if existing is not None:
            await delete_document(conn, existing.id)
        document_id = await insert_document(
            conn,
            source=source,
            doc_type=doc_type,
            content_hash=content_hash,
            title=doc.title,
            metadata={**doc.metadata, 'chunker_mode': settings.chunker_mode},
        )
        await insert_chunks(conn, document_id, records)

    status: IngestStatus = 'created' if existing is None else 'updated'
    logger.info('%s: %s, %s, чанков %d', source, status, doc_type, len(records))
    return IngestResult(document_id, source, doc_type, status, len(records), len(retrievable))
