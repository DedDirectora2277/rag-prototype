"""SQL гибридного поиска: вектор (HNSW) + полнотекст (tsvector), склейка через RRF.

Замечание: `ts_rank_cd` — не BM25 (нет IDF и нормализации
по длине документа как в Okapi). Это осознанное упрощение в рамках стека
PostgreSQL; альтернатива — ParadeDB `pg_search`.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import asyncpg

from app.db.client import Executor

# Параметры: $1 эмбеддинг запроса, $2 текст запроса, $3 doc_types, $4 фильтр metadata,
# $5 top-N вектора, $6 top-N полнотекста, $7 k в RRF, $8 итоговый top-N.
_FILTER = """
    c.is_retrievable
    AND ($3::text[] IS NULL
         OR c.document_id IN (SELECT id FROM documents WHERE doc_type = ANY($3::text[])))
    AND ($4::jsonb IS NULL OR c.metadata @> $4::jsonb)
"""

# Чанки хранятся с разными ts_config, поэтому запрос строится в конфигурации самого чанка.
# OR по трём конфигурациям — индексируемое (GIN) надмножество точного условия.
_FTS_MATCH = """
    (c.tsv @@ websearch_to_tsquery('russian', $2)
     OR c.tsv @@ websearch_to_tsquery('english', $2)
     OR c.tsv @@ websearch_to_tsquery('simple', $2))
    AND c.tsv @@ websearch_to_tsquery(c.ts_config, $2)
"""

HYBRID_SQL = f"""
WITH vec AS (
    SELECT id, distance, ROW_NUMBER() OVER (ORDER BY distance, id) AS rank
    FROM (
        SELECT c.id, c.embedding <=> $1 AS distance
        FROM chunks c
        WHERE {_FILTER}
        ORDER BY distance
        LIMIT $5
    ) v
),
fts AS (
    SELECT id, fts_score, ROW_NUMBER() OVER (ORDER BY fts_score DESC, id) AS rank
    FROM (
        SELECT c.id, ts_rank_cd(c.tsv, websearch_to_tsquery(c.ts_config, $2)) AS fts_score
        FROM chunks c
        WHERE {_FILTER} AND {_FTS_MATCH}
        ORDER BY fts_score DESC
        LIMIT $6
    ) f
),
fused AS (
    SELECT
        COALESCE(vec.id, fts.id) AS id,
        COALESCE(1.0::float8 / ($7 + vec.rank), 0)
            + COALESCE(1.0::float8 / ($7 + fts.rank), 0) AS score,
        vec.rank AS vec_rank,
        fts.rank AS fts_rank,
        vec.distance AS vec_distance,
        fts.fts_score
    FROM vec
    FULL OUTER JOIN fts ON fts.id = vec.id
)
SELECT
    c.id, c.document_id, c.parent_id, c.chunk_type, c.content, c.metadata,
    d.source, d.doc_type, d.title,
    f.score, f.vec_rank, f.fts_rank, f.vec_distance, f.fts_score
FROM fused f
JOIN chunks c ON c.id = f.id
JOIN documents d ON d.id = c.document_id
ORDER BY f.score DESC, c.id
LIMIT $8
"""

FETCH_CHUNKS_SQL = """
SELECT c.id, c.document_id, c.parent_id, c.chunk_type, c.content, c.metadata
FROM chunks c
WHERE c.id = ANY($1::bigint[])
"""


@dataclass(frozen=True, slots=True)
class SearchHit:
    """Найденный чанк со скором RRF и диагностикой по каждому каналу.

    Attributes:
        chunk_id: Идентификатор чанка.
        document_id: Идентификатор документа.
        parent_id: Идентификатор parent-чанка, если есть.
        chunk_type: Тип чанка.
        content: Текст чанка.
        metadata: Метаданные чанка.
        source: Источник документа.
        doc_type: Домен документа.
        title: Заголовок документа.
        score: Скор RRF.
        vec_rank: Ранг в векторной выдаче (1-based) или `None`.
        fts_rank: Ранг в полнотекстовой выдаче (1-based) или `None`.
        vec_distance: Косинусное расстояние или `None`.
        fts_score: Значение `ts_rank_cd` или `None`.
    """

    chunk_id: int
    document_id: int
    parent_id: int | None
    chunk_type: str
    content: str
    metadata: dict[str, Any]
    source: str
    doc_type: str
    title: str | None
    score: float
    vec_rank: int | None
    fts_rank: int | None
    vec_distance: float | None
    fts_score: float | None


@dataclass(frozen=True, slots=True)
class StoredChunk:
    """Чанк, прочитанный по идентификатору (например, parent)."""

    id: int
    document_id: int
    parent_id: int | None
    chunk_type: str
    content: str
    metadata: dict[str, Any]


def _to_hit(row: asyncpg.Record) -> SearchHit:
    return SearchHit(
        chunk_id=row['id'],
        document_id=row['document_id'],
        parent_id=row['parent_id'],
        chunk_type=row['chunk_type'],
        content=row['content'],
        metadata=row['metadata'],
        source=row['source'],
        doc_type=row['doc_type'],
        title=row['title'],
        score=row['score'],
        vec_rank=row['vec_rank'],
        fts_rank=row['fts_rank'],
        vec_distance=row['vec_distance'],
        fts_score=row['fts_score'],
    )


async def hybrid_search(
    db: Executor,
    *,
    embedding: Sequence[float] | None,
    query: str,
    top_n: int,
    vector_top_n: int,
    fts_top_n: int,
    rrf_k: int = 60,
    doc_types: Sequence[str] | None = None,
    metadata_filter: Mapping[str, Any] | None = None,
) -> list[SearchHit]:
    """Гибридный поиск одним запросом: top-N вектора и top-N FTS, склейка RRF.

    RRF: `score = Σ 1 / (k + rank)` по каналам, где чанк найден.

    Args:
        db: Пул или соединение.
        embedding: Эмбеддинг запроса (`None` отключает векторный канал).
        query: Текст запроса для `websearch_to_tsquery`.
        top_n: Сколько чанков вернуть после склейки.
        vector_top_n: Глубина векторного канала (0 — канал выключен).
        fts_top_n: Глубина полнотекстового канала (0 — канал выключен).
        rrf_k: Константа k в RRF.
        doc_types: Фильтр по доменам документов.
        metadata_filter: Фильтр `metadata @> ...` по чанкам.

    Returns:
        Чанки в порядке убывания скора RRF.
    """
    if embedding is None:
        vector_top_n = 0
    rows = await db.fetch(
        HYBRID_SQL,
        embedding,
        query,
        list(doc_types) if doc_types is not None else None,
        dict(metadata_filter) if metadata_filter is not None else None,
        vector_top_n,
        fts_top_n,
        rrf_k,
        top_n,
    )
    return [_to_hit(row) for row in rows]


async def vector_only(
    db: Executor,
    *,
    embedding: Sequence[float],
    top_n: int,
    doc_types: Sequence[str] | None = None,
    metadata_filter: Mapping[str, Any] | None = None,
) -> list[SearchHit]:
    """Только векторный канал (для ablation); порядок — по косинусному расстоянию.

    Args:
        db: Пул или соединение.
        embedding: Эмбеддинг запроса.
        top_n: Сколько чанков вернуть.
        doc_types: Фильтр по доменам документов.
        metadata_filter: Фильтр `metadata @> ...` по чанкам.

    Returns:
        Ближайшие чанки.
    """
    return await hybrid_search(
        db,
        embedding=embedding,
        query='',
        top_n=top_n,
        vector_top_n=top_n,
        fts_top_n=0,
        doc_types=doc_types,
        metadata_filter=metadata_filter,
    )


async def fts_only(
    db: Executor,
    *,
    query: str,
    top_n: int,
    doc_types: Sequence[str] | None = None,
    metadata_filter: Mapping[str, Any] | None = None,
) -> list[SearchHit]:
    """Только полнотекстовый канал (для ablation); порядок — по `ts_rank_cd`.

    Args:
        db: Пул или соединение.
        query: Текст запроса.
        top_n: Сколько чанков вернуть.
        doc_types: Фильтр по доменам документов.
        metadata_filter: Фильтр `metadata @> ...` по чанкам.

    Returns:
        Наиболее релевантные по FTS чанки.
    """
    return await hybrid_search(
        db,
        embedding=None,
        query=query,
        top_n=top_n,
        vector_top_n=0,
        fts_top_n=top_n,
        doc_types=doc_types,
        metadata_filter=metadata_filter,
    )


async def fetch_parents(db: Executor, parent_ids: Sequence[int]) -> dict[int, StoredChunk]:
    """Подтягивает parent-чанки по идентификаторам.

    Args:
        db: Пул или соединение.
        parent_ids: Идентификаторы родителей (дубликаты допустимы).

    Returns:
        Словарь `id → чанк`.
    """
    if not parent_ids:
        return {}
    rows = await db.fetch(FETCH_CHUNKS_SQL, sorted(set(parent_ids)))
    return {
        row['id']: StoredChunk(
            id=row['id'],
            document_id=row['document_id'],
            parent_id=row['parent_id'],
            chunk_type=row['chunk_type'],
            content=row['content'],
            metadata=row['metadata'],
        )
        for row in rows
    }
