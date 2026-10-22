import json
import math
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from openai import AsyncOpenAI

from app.config import Settings
from app.db.client import Pool, create_pool, init_db
from app.retrieval.embedder import Embedder
from app.retrieval.reranker import Reranker

# Маленькая размерность, чтобы тесты не зависели от реального эмбеддера.
TEST_EMBED_DIM = 4


@asynccontextmanager
async def _schema_pool(schema: str) -> AsyncIterator[Pool]:
    settings = Settings()
    try:
        pool = await create_pool(settings)
    except OSError as exc:
        pytest.skip(f'PostgreSQL недоступен ({settings.database_dsn}): {exc}')

    # Отдельная схема: тесты не трогают рабочие таблицы и могут менять размерность.
    await pool.execute(f'DROP SCHEMA IF EXISTS {schema} CASCADE; CREATE SCHEMA {schema}')
    await pool.close()

    settings = Settings(
        database_dsn=_with_search_path(settings.database_dsn, f'{schema},public'),
        embed_dim=TEST_EMBED_DIM,
    )
    pool = await create_pool(settings)
    await init_db(pool, settings.embed_dim)
    try:
        yield pool
    finally:
        await pool.execute(f'DROP SCHEMA {schema} CASCADE')
        await pool.close()


@pytest.fixture(scope='session')
async def db_pool() -> AsyncIterator[Pool]:
    async with _schema_pool('rag_test') as pool:
        yield pool


@pytest.fixture(scope='session')
async def _e2e_session_pool() -> AsyncIterator[Pool]:
    async with _schema_pool('rag_e2e') as pool:
        yield pool


@pytest.fixture
async def e2e_pool(_e2e_session_pool: Pool) -> Pool:
    """Пул со своей схемой, очищаемой перед каждым тестом."""
    await _e2e_session_pool.execute('TRUNCATE documents RESTART IDENTITY CASCADE')
    return _e2e_session_pool


def _with_search_path(dsn: str, search_path: str) -> str:
    # asyncpg передаёт неизвестные параметры DSN как server_settings.
    sep = '&' if '?' in dsn else '?'
    return f'{dsn}{sep}search_path={search_path.replace(",", "%2C")}'


# --- Фейковый LiteLLM -------------------------------------------------------------

# Оси «смыслов» фейкового эмбеддера: основы слов, которые тянут вектор к оси.
EMBED_AXES = (
    ('оплат', 'стоимост', 'цен', 'руб', 'неустой', 'пен'),
    ('постав', 'срок', 'достав', 'склад'),
    ('def ', 'class ', 'return', 'функци', 'import'),
    ('выручк', 'прибыл', 'расход', 'себестоим'),
)
_WORD = re.compile(r'\w{4,}')


def fake_embedding(text: str) -> list[float]:
    """Детерминированный 4-мерный «эмбеддинг» по ключевым основам."""
    low = text.lower()
    vec = [0.05 + sum(low.count(stem) for stem in axis) for axis in EMBED_AXES]
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec]


def fake_rerank_score(query: str, doc: str) -> float:
    """Доля основ (5 букв) слов запроса, встречающихся в документе."""
    stems = {w[:5] for w in _WORD.findall(query.lower())}
    low = doc.lower()
    return sum(stem in low for stem in stems) / max(len(stems), 1)


class FakeLiteLLM:
    """Обработчик `httpx.MockTransport`: `/v1/embeddings`, `/v1/chat/completions`, `/rerank`."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, Any]]] = []
        self.rerank_available = True
        self.answer = 'Ответ по фрагменту [1].'

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b'{}')
        path = request.url.path
        self.requests.append((path, body))
        if path.endswith('/embeddings'):
            inputs = body['input']
            return httpx.Response(
                200,
                json={
                    'object': 'list',
                    'model': body['model'],
                    # Обратный порядок: эмбеддер обязан сортировать по index.
                    'data': [
                        {'object': 'embedding', 'index': i, 'embedding': fake_embedding(t)}
                        for i, t in reversed(list(enumerate(inputs)))
                    ],
                    'usage': {'prompt_tokens': 0, 'total_tokens': 0},
                },
            )
        if path.endswith('/rerank'):
            if not self.rerank_available:
                return httpx.Response(503, json={'error': 'down'})
            scores = [fake_rerank_score(body['query'], d) for d in body['documents']]
            # Как LiteLLM: top_n игнорируется, порядок — по убыванию скора.
            results = sorted(
                ({'index': i, 'relevance_score': s} for i, s in enumerate(scores)),
                key=lambda r: -float(r['relevance_score']),
            )
            return httpx.Response(200, json={'id': 'r', 'results': results})
        if path.endswith('/chat/completions'):
            return httpx.Response(
                200,
                json={
                    'id': 'c',
                    'object': 'chat.completion',
                    'created': 0,
                    'model': body['model'],
                    'choices': [
                        {
                            'index': 0,
                            'finish_reason': 'stop',
                            'message': {'role': 'assistant', 'content': self.answer},
                        }
                    ],
                },
            )
        return httpx.Response(404)


@pytest.fixture
def fake_litellm() -> FakeLiteLLM:
    return FakeLiteLLM()


@pytest.fixture
def test_settings() -> Settings:
    return Settings(embed_dim=TEST_EMBED_DIM, litellm_url='http://litellm')


@pytest.fixture
async def llm_client(fake_litellm: FakeLiteLLM) -> AsyncIterator[AsyncOpenAI]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake_litellm))
    client = AsyncOpenAI(base_url='http://litellm/v1', api_key='test', http_client=http)
    yield client
    await client.close()


@pytest.fixture
def embedder(llm_client: AsyncOpenAI, test_settings: Settings) -> Embedder:
    return Embedder(llm_client, 'embed', TEST_EMBED_DIM, batch_size=2, concurrency=2)


@pytest.fixture
async def reranker(fake_litellm: FakeLiteLLM) -> AsyncIterator[Reranker]:
    http = httpx.AsyncClient(base_url='http://litellm', transport=httpx.MockTransport(fake_litellm))
    yield Reranker(http, 'rerank')
    await http.aclose()
