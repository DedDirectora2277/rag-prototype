"""FastAPI-сервер прототипа: `/ingest`, `/query`, `/health`.

Запуск: `uvicorn app.api.main:app`.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import httpx
import openai
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field

from app.config import Settings, get_settings
from app.db.client import Pool, create_pool, init_db
from app.generation import generate_answer
from app.ingest.parsers import UnsupportedFormatError
from app.ingest.pipeline import IngestResult, ingest_bytes, ingest_path
from app.ingest.router import DocType
from app.retrieval.embedder import Embedder
from app.retrieval.hybrid import Retriever
from app.retrieval.reranker import Reranker

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class Services:
    """Зависимости обработчиков; в тестах подменяются фейками."""

    settings: Settings
    pool: Pool
    llm: AsyncOpenAI
    embedder: Embedder
    retriever: Retriever
    http: httpx.AsyncClient | None = None  # клиент реранкера, закрывается при остановке


class QueryConfig(BaseModel):
    """Переопределения настроек retrieval для одного запроса (ablation из бенчмарка)."""

    model_config = ConfigDict(extra='forbid')

    use_fts: bool | None = None
    use_rerank: bool | None = None
    use_parent_expansion: bool | None = None
    vector_top_n: int | None = Field(default=None, ge=1)
    fts_top_n: int | None = Field(default=None, ge=1)
    hybrid_top_n: int | None = Field(default=None, ge=1)
    rrf_k: int | None = Field(default=None, ge=1)
    rerank_top_n: int | None = Field(default=None, ge=1)


class QueryFilters(BaseModel):
    """Фильтры поиска."""

    model_config = ConfigDict(extra='forbid')

    doc_types: list[DocType] | None = None
    metadata: dict[str, Any] | None = None


class QueryRequest(BaseModel):
    """Тело `POST /query`."""

    question: str = Field(min_length=1)
    filters: QueryFilters | None = None
    config_overrides: QueryConfig | None = None


class ContextOut(BaseModel):
    """Контекст в ответе; список `text` — это `retrieved_contexts` для RAGAS."""

    text: str
    source: str
    doc_type: str
    title: str | None
    chunk_id: int
    chunk_type: str
    score: float
    rrf_score: float
    rerank_score: float | None
    metadata: dict[str, Any]


class QueryResponse(BaseModel):
    """Ответ `POST /query`."""

    answer: str
    contexts: list[ContextOut]


class IngestResponse(BaseModel):
    """Ответ `POST /ingest`."""

    document_id: int
    source: str
    doc_type: str
    status: str
    chunks: int
    retrievable: int


async def build_services(settings: Settings) -> Services:
    """Создаёт пул, клиентов LiteLLM и retriever; применяет схему БД.

    Args:
        settings: Настройки приложения.

    Returns:
        Готовые сервисы.
    """
    pool = await create_pool(settings)
    await init_db(pool, settings.embed_dim)
    llm = AsyncOpenAI(base_url=f'{settings.litellm_url}/v1', api_key=settings.litellm_api_key)
    embedder = Embedder.from_settings(llm, settings)
    http = Reranker.make_client(settings)
    reranker = Reranker(http, settings.rerank_model)
    retriever = Retriever(pool, embedder, reranker, settings)
    return Services(settings, pool, llm, embedder, retriever, http)


def create_app(services: Services | None = None) -> FastAPI:
    """Создаёт приложение.

    Args:
        services: Готовые сервисы (в тестах); `None` — создать при старте и закрыть
            при остановке.

    Returns:
        Приложение FastAPI.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if services is not None:
            yield
            return
        own = await build_services(get_settings())
        app.state.services = own
        try:
            yield
        finally:
            await own.pool.close()
            await own.llm.close()
            if own.http is not None:
                await own.http.aclose()

    app = FastAPI(title='rag-proto', lifespan=lifespan)
    if services is not None:
        # ASGITransport в тестах не запускает lifespan.
        app.state.services = services

    @app.get('/health')
    async def health(request: Request) -> dict[str, str]:
        svc: Services = request.app.state.services
        await svc.pool.fetchval('SELECT 1')
        return {'status': 'ok'}

    @app.post('/ingest')
    async def ingest(
        request: Request,
        file: Annotated[UploadFile | None, File()] = None,
        path: Annotated[str | None, Form()] = None,
        source: Annotated[str | None, Form()] = None,
        doc_type: Annotated[DocType | None, Form()] = None,
        force: Annotated[bool, Form()] = False,
    ) -> IngestResponse:
        """Загружает документ: multipart-файл или путь на машине сервера."""
        svc: Services = request.app.state.services
        if (file is None) == (path is None):
            raise HTTPException(422, 'нужно передать ровно одно из полей: file или path')
        try:
            if file is not None:
                result: IngestResult = await ingest_bytes(
                    svc.pool,
                    svc.embedder,
                    svc.settings,
                    await file.read(),
                    filename=file.filename or 'upload.txt',
                    source=source,
                    doc_type=doc_type,
                    force=force,
                )
            else:
                result = await ingest_path(
                    svc.pool,
                    svc.embedder,
                    svc.settings,
                    Path(path or ''),
                    doc_type=doc_type,
                    force=force,
                )
        except (FileNotFoundError, IsADirectoryError) as exc:
            raise HTTPException(404, f'файл не найден: {path}') from exc
        except UnsupportedFormatError as exc:
            raise HTTPException(415, str(exc)) from exc
        except openai.APIError as exc:
            raise HTTPException(502, f'ошибка LiteLLM: {exc}') from exc
        return IngestResponse(
            document_id=result.document_id,
            source=result.source,
            doc_type=result.doc_type,
            status=result.status,
            chunks=result.chunks,
            retrievable=result.retrievable,
        )

    @app.post('/query')
    async def query(request: Request, body: QueryRequest) -> QueryResponse:
        """Отвечает на вопрос и возвращает использованные контексты."""
        svc: Services = request.app.state.services
        cfg = svc.settings
        if body.config_overrides is not None:
            cfg = cfg.model_copy(update=body.config_overrides.model_dump(exclude_none=True))
        filters = body.filters or QueryFilters()
        try:
            contexts = await svc.retriever.retrieve(
                body.question,
                doc_types=filters.doc_types,
                metadata_filter=filters.metadata,
                settings=cfg,
            )
            answer = await generate_answer(svc.llm, cfg.chat_model, body.question, contexts)
        except openai.APIError as exc:
            raise HTTPException(502, f'ошибка LiteLLM: {exc}') from exc
        return QueryResponse(
            answer=answer,
            contexts=[
                ContextOut(
                    text=c.content,
                    source=c.source,
                    doc_type=c.doc_type,
                    title=c.title,
                    chunk_id=c.chunk_id,
                    chunk_type=c.chunk_type,
                    score=c.score,
                    rrf_score=c.rrf_score,
                    rerank_score=c.rerank_score,
                    metadata=c.metadata,
                )
                for c in contexts
            ],
        )

    return app


app = create_app()
