"""Сквозной путь ingest → retrieve → /query на живом Postgres и фейковом LiteLLM."""

from pathlib import Path

import httpx
import pytest
from openai import AsyncOpenAI

from app.api.main import Services, create_app
from app.config import Settings
from app.db.client import Pool
from app.ingest.pipeline import ingest_bytes, ingest_path
from app.retrieval.embedder import Embedder
from app.retrieval.hybrid import Retriever
from app.retrieval.reranker import Reranker

from conftest import FakeLiteLLM

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent / 'fixtures'
PENALTY_QUESTION = 'Какая неустойка за просрочку поставки?'


@pytest.fixture
async def corpus(e2e_pool: Pool, embedder: Embedder, test_settings: Settings) -> None:
    for name in ['contract.txt', 'npa.txt', 'report.csv', 'sample_module.py']:
        await ingest_path(e2e_pool, embedder, test_settings, FIXTURES / name)


@pytest.fixture
def retriever(
    e2e_pool: Pool, embedder: Embedder, reranker: Reranker, test_settings: Settings
) -> Retriever:
    return Retriever(e2e_pool, embedder, reranker, test_settings)


async def test_ingest_is_idempotent_by_content_hash(
    e2e_pool: Pool, embedder: Embedder, test_settings: Settings
) -> None:
    data = (FIXTURES / 'contract.txt').read_bytes()

    first = await ingest_bytes(e2e_pool, embedder, test_settings, data, filename='c.txt')
    again = await ingest_bytes(e2e_pool, embedder, test_settings, data, filename='c.txt')
    changed = await ingest_bytes(
        e2e_pool, embedder, test_settings, data + '\n7.1. Новый пункт.'.encode(), filename='c.txt'
    )

    assert (first.status, first.doc_type) == ('created', 'contract')
    assert 0 < first.retrievable < first.chunks  # parent-разделы не эмбеддятся
    assert (again.status, again.document_id, again.doc_type) == (
        'unchanged',
        first.document_id,
        'contract',
    )
    assert changed.status == 'updated'
    assert await e2e_pool.fetchval('SELECT count(*) FROM documents') == 1
    assert await e2e_pool.fetchval('SELECT count(*) FROM chunks') == changed.chunks
    stored_types = await e2e_pool.fetchval(
        'SELECT count(*) FROM chunks WHERE is_retrievable AND embedding IS NOT NULL'
    )
    assert stored_types == changed.retrievable


@pytest.mark.usefixtures('corpus')
async def test_parent_expansion_returns_section_once(retriever: Retriever) -> None:
    contexts = await retriever.retrieve(PENALTY_QUESTION, doc_types=['contract'])

    top = contexts[0]
    assert top.chunk_type == 'section'
    assert '5.1. За нарушение срока поставки' in top.content
    assert '5.3. Уплата неустойки' in top.content
    # Пункты 5.1 и 5.3 найдены оба, но раздел отдан один раз.
    assert len(top.matched_chunk_ids) >= 2
    assert len({c.chunk_id for c in contexts}) == len(contexts)
    assert top.rerank_score is not None
    assert top.score == top.rerank_score


@pytest.mark.usefixtures('corpus')
async def test_without_expansion_returns_clauses(
    retriever: Retriever, test_settings: Settings
) -> None:
    cfg = test_settings.model_copy(update={'use_parent_expansion': False, 'rerank_top_n': 3})

    contexts = await retriever.retrieve(PENALTY_QUESTION, doc_types=['contract'], settings=cfg)

    assert len(contexts) == 3
    assert {c.chunk_type for c in contexts} <= {'clause', 'section', 'preamble'}
    assert contexts[0].chunk_type == 'clause'
    assert all(c.matched_chunk_ids == [c.chunk_id] for c in contexts)


@pytest.mark.usefixtures('corpus')
async def test_rerank_fallback_keeps_rrf_order(
    retriever: Retriever, fake_litellm: FakeLiteLLM, test_settings: Settings
) -> None:
    fake_litellm.rerank_available = False
    cfg = test_settings.model_copy(update={'use_parent_expansion': False})

    contexts = await retriever.retrieve(PENALTY_QUESTION, settings=cfg)

    assert contexts
    assert all(c.rerank_score is None for c in contexts)
    assert [c.score for c in contexts] == sorted((c.rrf_score for c in contexts), reverse=True)


@pytest.mark.usefixtures('corpus')
async def test_doc_type_filter_and_code_identifier(retriever: Retriever) -> None:
    contexts = await retriever.retrieve('calculate_penalty', doc_types=['code'])

    assert contexts
    assert {c.doc_type for c in contexts} == {'code'}


@pytest.fixture
async def api(
    e2e_pool: Pool,
    llm_client: AsyncOpenAI,
    embedder: Embedder,
    retriever: Retriever,
    test_settings: Settings,
) -> httpx.AsyncClient:
    services = Services(test_settings, e2e_pool, llm_client, embedder, retriever)
    transport = httpx.ASGITransport(app=create_app(services))
    return httpx.AsyncClient(transport=transport, base_url='http://api')


async def test_api_ingest_and_query(api: httpx.AsyncClient, fake_litellm: FakeLiteLLM) -> None:
    async with api:
        health = await api.get('/health')
        ingested = await api.post(
            '/ingest',
            files={'file': ('contract.txt', (FIXTURES / 'contract.txt').read_bytes())},
            data={'source': 'uploads/contract.txt'},
        )
        answer = await api.post(
            '/query',
            json={
                'question': PENALTY_QUESTION,
                'filters': {'doc_types': ['contract']},
                'config_overrides': {'rerank_top_n': 2},
            },
        )

    assert health.json() == {'status': 'ok'}
    assert ingested.status_code == 200, ingested.text
    assert ingested.json()['source'] == 'uploads/contract.txt'
    assert ingested.json()['doc_type'] == 'contract'
    body = answer.json()
    assert answer.status_code == 200, body
    assert body['answer'] == fake_litellm.answer
    assert 1 <= len(body['contexts']) <= 2
    assert 'неустойк' in body['contexts'][0]['text']
    assert body['contexts'][0]['source'] == 'uploads/contract.txt'
    # Контексты из ответа попали в промпт под номерами [n].
    _, chat = next(r for r in fake_litellm.requests if r[0].endswith('/chat/completions'))
    assert '[1] ' in chat['messages'][1]['content']


@pytest.mark.parametrize(
    ('kwargs', 'status'),
    [
        ({'data': {'path': 'nope.txt'}}, 404),
        ({'files': {'file': ('a.png', b'\x89PNG')}}, 415),
        ({'files': {'file': ('a.txt', b'x')}, 'data': {'path': 'a.txt'}}, 422),
        ({}, 422),
    ],
)
async def test_api_ingest_errors(
    api: httpx.AsyncClient, kwargs: dict[str, dict[str, object]], status: int
) -> None:
    async with api:
        response = await api.post('/ingest', **kwargs)  # type: ignore[arg-type]

    assert response.status_code == status, response.text


async def test_api_query_rejects_unknown_override(api: httpx.AsyncClient) -> None:
    async with api:
        response = await api.post(
            '/query', json={'question': 'вопрос', 'config_overrides': {'chat_model': 'gpt'}}
        )

    assert response.status_code == 422
