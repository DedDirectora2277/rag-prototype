# asyncpg-классы обобщены только в стабах, поэтому аннотации не вычисляются в рантайме.
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import asyncpg
from pgvector.asyncpg import register_vector

from app.config import Settings

# Лимит HNSW-индекса pgvector для типа vector.
HNSW_MAX_DIM = 2000
SCHEMA_PATH = Path(__file__).with_name('schema.sql')

type Pool = asyncpg.Pool[asyncpg.Record]
# pool.acquire() отдаёт прокси, а не сам Connection.
type Connection = (
    asyncpg.Connection[asyncpg.Record] | asyncpg.pool.PoolConnectionProxy[asyncpg.Record]
)
type Executor = Pool | Connection


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    """Чанк, готовый к записи в БД.

    Attributes:
        content: Текст чанка.
        chunk_type: Тип чанка (`text`, `clause`, `function`, `table_rows`, ...).
        ts_config: Конфигурация полнотекстового поиска (`russian`, `english`, `simple`).
        embedding: Вектор; обязателен для retrievable-чанков.
        is_retrievable: Участвует ли чанк в поиске (parent-чанки — нет).
        parent_index: Индекс родителя в той же последовательности чанков.
        metadata: Произвольные метаданные (номера пунктов, путь файла и т.п.).
    """

    content: str
    chunk_type: str
    ts_config: str = 'simple'
    embedding: Sequence[float] | None = None
    is_retrievable: bool = True
    parent_index: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StoredDocument:
    """Краткие сведения о документе, уже записанном в БД."""

    id: int
    source: str
    doc_type: str
    content_hash: str


async def _init_connection(conn: asyncpg.Connection[asyncpg.Record]) -> None:
    await register_vector(conn)
    await conn.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')
    # Без итеративного сканирования фильтры по doc_type/metadata срезают выдачу HNSW.
    await conn.execute("SET hnsw.iterative_scan = 'relaxed_order'")


async def create_pool(settings: Settings) -> Pool:
    """Создаёт пул соединений с зарегистрированными типами `vector` и `jsonb`.

    Расширение `vector` создаётся заранее, иначе регистрация кодека упадёт.

    Args:
        settings: Настройки приложения.

    Returns:
        Пул соединений asyncpg.
    """
    conn = await asyncpg.connect(settings.database_dsn)
    try:
        await conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
    finally:
        await conn.close()

    return await asyncpg.create_pool(
        settings.database_dsn,
        min_size=settings.db_pool_min_size,
        max_size=settings.db_pool_max_size,
        init=_init_connection,
    )


async def init_db(db: Executor, embed_dim: int) -> None:
    """Применяет `schema.sql` с нужной размерностью эмбеддингов.

    Args:
        db: Пул или соединение.
        embed_dim: Размерность эмбеддингов.

    Raises:
        ValueError: Если размерность превышает лимит HNSW для `vector`.
    """
    if not 0 < embed_dim <= HNSW_MAX_DIM:
        raise ValueError(
            f'embed_dim={embed_dim} вне диапазона 1..{HNSW_MAX_DIM}: '
            'передайте dimensions= в API эмбеддингов или перейдите на halfvec'
        )
    sql = SCHEMA_PATH.read_text(encoding='utf-8').replace('{embed_dim}', str(embed_dim))
    await db.execute(sql)


async def get_document_by_source(db: Executor, source: str) -> StoredDocument | None:
    """Ищет документ по источнику (для идемпотентного ingest).

    Args:
        db: Пул или соединение.
        source: Путь или URI документа.

    Returns:
        Документ или `None`, если он ещё не загружен.
    """
    row = await db.fetchrow(
        'SELECT id, source, doc_type, content_hash FROM documents WHERE source = $1', source
    )
    if row is None:
        return None
    return StoredDocument(
        id=row['id'],
        source=row['source'],
        doc_type=row['doc_type'],
        content_hash=row['content_hash'],
    )


async def insert_document(
    db: Executor,
    *,
    source: str,
    doc_type: str,
    content_hash: str,
    title: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> int:
    """Создаёт запись документа.

    Args:
        db: Пул или соединение.
        source: Путь или URI документа (уникален).
        doc_type: Домен документа (`contract`, `code`, `table`, `text`).
        content_hash: Хеш содержимого для идемпотентности.
        title: Заголовок документа.
        metadata: Произвольные метаданные.

    Returns:
        Идентификатор документа.
    """
    document_id: int = await db.fetchval(
        """
        INSERT INTO documents (source, doc_type, title, content_hash, metadata)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """,
        source,
        doc_type,
        title,
        content_hash,
        dict(metadata or {}),
    )
    return document_id


async def insert_chunks(
    conn: Connection, document_id: int, chunks: Sequence[ChunkRecord]
) -> list[int]:
    """Записывает чанки документа одним `executemany`.

    Идентификаторы выделяются заранее из последовательности, поэтому ссылки
    child → parent (`parent_index`) разрешаются без построчных INSERT.
    Вызывать внутри транзакции.

    Args:
        conn: Соединение (не пул: нужна одна транзакция).
        document_id: Идентификатор документа.
        chunks: Чанки; родитель должен стоять раньше своих детей.

    Returns:
        Идентификаторы чанков в порядке `chunks`.

    Raises:
        ValueError: Если `parent_index` не указывает на более ранний чанк.
    """
    if not chunks:
        return []

    ids: list[int] = [
        row[0]
        for row in await conn.fetch(
            "SELECT nextval(pg_get_serial_sequence('chunks', 'id')) FROM generate_series(1, $1)",
            len(chunks),
        )
    ]

    records = []
    for i, chunk in enumerate(chunks):
        parent_id = None
        if chunk.parent_index is not None:
            if not 0 <= chunk.parent_index < i:
                raise ValueError(f'чанк {i}: parent_index={chunk.parent_index} не раньше чанка')
            parent_id = ids[chunk.parent_index]
        records.append(
            (
                ids[i],
                document_id,
                parent_id,
                i,
                chunk.chunk_type,
                chunk.content,
                chunk.ts_config,
                chunk.embedding,
                chunk.is_retrievable,
                dict(chunk.metadata),
            )
        )

    await conn.executemany(
        """
        INSERT INTO chunks (
            id, document_id, parent_id, chunk_index, chunk_type, content,
            ts_config, embedding, is_retrievable, metadata
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7::text::regconfig, $8, $9, $10)
        """,
        records,
    )
    return ids


async def delete_document(db: Executor, document_id: int) -> bool:
    """Удаляет документ вместе с чанками (каскадно).

    Args:
        db: Пул или соединение.
        document_id: Идентификатор документа.

    Returns:
        `True`, если документ существовал.
    """
    status = await db.execute('DELETE FROM documents WHERE id = $1', document_id)
    return status != 'DELETE 0'
