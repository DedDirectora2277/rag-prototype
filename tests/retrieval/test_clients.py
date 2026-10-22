import pytest
from openai import AsyncOpenAI

from app.generation import NO_ANSWER, build_messages, generate_answer
from app.retrieval.embedder import Embedder
from app.retrieval.hybrid import RetrievedChunk
from app.retrieval.reranker import Reranker

from conftest import FakeLiteLLM, fake_embedding


async def test_embedder_batches_and_keeps_order(
    embedder: Embedder, fake_litellm: FakeLiteLLM
) -> None:
    texts = ['оплата', 'поставка', 'def f(): return 1', 'выручка', 'неустойка']

    vectors = await embedder.embed(texts)

    assert vectors == [fake_embedding(t) for t in texts]
    # batch_size=2 → три запроса; уходят параллельно, порядок прихода не гарантирован.
    assert sorted(len(body['input']) for _, body in fake_litellm.requests) == [1, 2, 2]


async def test_embedder_checks_dimension(llm_client: AsyncOpenAI) -> None:
    embedder = Embedder(llm_client, 'embed', dim=1024)

    with pytest.raises(ValueError, match='размерность'):
        await embedder.embed_query('запрос')


async def test_embedder_empty_input_makes_no_requests(
    embedder: Embedder, fake_litellm: FakeLiteLLM
) -> None:
    assert await embedder.embed([]) == []
    assert fake_litellm.requests == []


async def test_reranker_sorts_and_cuts_top_n(reranker: Reranker, fake_litellm: FakeLiteLLM) -> None:
    docs = ['про выручку', 'срок поставки товара', 'поставка']

    ranked = await reranker.rerank('срок поставки', docs, top_n=2)

    assert [i for i, _ in ranked] == [1, 2]
    assert ranked[0][1] >= ranked[1][1]
    path, body = fake_litellm.requests[0]
    assert path == '/rerank'
    assert body['documents'] == docs


async def test_reranker_unavailable_returns_none(
    reranker: Reranker, fake_litellm: FakeLiteLLM
) -> None:
    fake_litellm.rerank_available = False

    assert await reranker.rerank('запрос', ['документ']) is None


def _ctx(n: int, content: str, title: str | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=n,
        content=content,
        chunk_type='clause',
        metadata={},
        source=f'docs/{n}.txt',
        doc_type='contract',
        title=title,
        score=1.0,
        rrf_score=0.1,
        rerank_score=None,
    )


def test_build_messages_numbers_contexts() -> None:
    messages = build_messages(
        'Какой срок?', [_ctx(1, 'Срок 20 дней.', 'Договор'), _ctx(2, 'Цена.')]
    )

    user = str(messages[1]['content'])
    assert '[1] Договор (docs/1.txt)\nСрок 20 дней.' in user
    assert '[2] docs/2.txt\nЦена.' in user
    assert user.endswith('Вопрос: Какой срок?')
    assert NO_ANSWER in str(messages[0]['content'])


async def test_generate_answer_without_contexts_skips_llm(
    llm_client: AsyncOpenAI, fake_litellm: FakeLiteLLM
) -> None:
    assert await generate_answer(llm_client, 'chat', 'вопрос', []) == NO_ANSWER
    assert fake_litellm.requests == []


async def test_generate_answer_calls_chat_with_zero_temperature(
    llm_client: AsyncOpenAI, fake_litellm: FakeLiteLLM
) -> None:
    answer = await generate_answer(llm_client, 'chat', 'Какой срок?', [_ctx(1, 'Срок 20 дней.')])

    assert answer == fake_litellm.answer
    path, body = fake_litellm.requests[0]
    assert path.endswith('/chat/completions')
    assert body['model'] == 'chat'
    assert body['temperature'] == 0.0
