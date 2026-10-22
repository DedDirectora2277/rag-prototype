"""Гибридный retrieval: эмбеддинг запроса → SQL с RRF → rerank → parent-expansion.

Реранкер оценивает найденные (child) чанки, а не их parent: parent бывает в разы
длиннее (раздел договора, таблица целиком), что и медленно, и хуже для кросс-энкодера.
Parent подставляется уже после переранжирования, дубли по parent схлопываются.
"""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.config import Settings
from app.db.client import Pool
from app.db.queries import SearchHit, fetch_parents, hybrid_search
from app.retrieval.embedder import Embedder
from app.retrieval.reranker import Reranker

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievedChunk:
    """Контекст для генерации.

    Attributes:
        chunk_id: Идентификатор чанка контекста (parent, если была подстановка).
        content: Текст контекста.
        chunk_type: Тип чанка контекста.
        metadata: Метаданные чанка контекста.
        source: Источник документа.
        doc_type: Домен документа.
        title: Заголовок документа.
        score: Итоговый скор: реранкера, если он отработал, иначе RRF.
        rrf_score: Скор RRF лучшего найденного child.
        rerank_score: Скор реранкера лучшего найденного child или `None`.
        matched_chunk_ids: Найденные поиском чанки, которые привели к этому контексту.
    """

    chunk_id: int
    content: str
    chunk_type: str
    metadata: dict[str, Any]
    source: str
    doc_type: str
    title: str | None
    score: float
    rrf_score: float
    rerank_score: float | None
    matched_chunk_ids: list[int] = field(default_factory=list)


class Retriever:
    """Гибридный поиск с переключаемыми этапами для ablation.

    Args:
        pool: Пул соединений.
        embedder: Эмбеддер запросов.
        reranker: Реранкер; `None` — переранжирование недоступно.
        settings: Настройки по умолчанию.
    """

    def __init__(
        self, pool: Pool, embedder: Embedder, reranker: Reranker | None, settings: Settings
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._reranker = reranker
        self.settings = settings

    async def retrieve(
        self,
        query: str,
        *,
        doc_types: Sequence[str] | None = None,
        metadata_filter: Mapping[str, Any] | None = None,
        settings: Settings | None = None,
    ) -> list[RetrievedChunk]:
        """Находит контексты для запроса.

        Args:
            query: Запрос пользователя.
            doc_types: Фильтр по доменам документов.
            metadata_filter: Фильтр `metadata @> ...` по чанкам.
            settings: Настройки этого запроса (флаги ablation, top-k); по умолчанию — общие.

        Returns:
            До `settings.rerank_top_n` контекстов по убыванию релевантности.
        """
        cfg = settings or self.settings
        embedding = await self._embedder.embed_query(query)
        hits = await hybrid_search(
            self._pool,
            embedding=embedding,
            query=query,
            top_n=cfg.hybrid_top_n,
            vector_top_n=cfg.vector_top_n,
            fts_top_n=cfg.fts_top_n if cfg.use_fts else 0,
            rrf_k=cfg.rrf_k,
            doc_types=doc_types,
            metadata_filter=metadata_filter,
        )
        if not hits:
            return []

        rerank_scores: list[float | None] = [None] * len(hits)
        order = list(range(len(hits)))
        if cfg.use_rerank and self._reranker is not None:
            # Все кандидаты: после схлопывания по parent может понадобиться больше top_n.
            ranked = await self._reranker.rerank(query, [hit.content for hit in hits])
            if ranked is not None:
                order = [index for index, _ in ranked]
                for index, score in ranked:
                    rerank_scores[index] = score

        return await self._build_contexts(
            [(hits[i], rerank_scores[i]) for i in order], cfg.rerank_top_n, cfg.use_parent_expansion
        )

    async def _build_contexts(
        self, ranked: list[tuple[SearchHit, float | None]], top_n: int, expand: bool
    ) -> list[RetrievedChunk]:
        parents = (
            await fetch_parents(self._pool, [h.parent_id for h, _ in ranked if h.parent_id])
            if expand
            else {}
        )
        contexts: dict[int, RetrievedChunk] = {}
        for hit, rerank_score in ranked:
            parent = parents.get(hit.parent_id) if hit.parent_id is not None else None
            key = parent.id if parent is not None else hit.chunk_id
            if key in contexts:
                contexts[key].matched_chunk_ids.append(hit.chunk_id)
                continue
            if len(contexts) >= top_n:
                continue
            contexts[key] = RetrievedChunk(
                chunk_id=key,
                content=parent.content if parent is not None else hit.content,
                chunk_type=parent.chunk_type if parent is not None else hit.chunk_type,
                metadata=parent.metadata if parent is not None else hit.metadata,
                source=hit.source,
                doc_type=hit.doc_type,
                title=hit.title,
                score=rerank_score if rerank_score is not None else hit.score,
                rrf_score=hit.score,
                rerank_score=rerank_score,
                matched_chunk_ids=[hit.chunk_id],
            )
        return list(contexts.values())
