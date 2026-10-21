from dataclasses import dataclass

import pytest

from app.db.client import (
    ChunkRecord,
    Pool,
    delete_document,
    get_document_by_source,
    init_db,
    insert_chunks,
    insert_document,
)
from app.db.queries import SearchHit, fetch_parents, fts_only, hybrid_search, vector_only

pytestmark = pytest.mark.integration

# Оси «смыслов» для синтетических 4-мерных эмбеддингов.
PENALTY = [1.0, 0.0, 0.0, 0.0]
DELIVERY = [0.0, 1.0, 0.0, 0.0]
CODE = [0.0, 0.0, 1.0, 0.0]
TABLE = [0.0, 0.0, 0.0, 1.0]


@dataclass(frozen=True)
class Corpus:
    contract_id: int
    code_id: int
    chunk_ids: dict[str, int]


@pytest.fixture(scope='module')
async def corpus(db_pool: Pool) -> Corpus:
    async with db_pool.acquire() as conn, conn.transaction():
        contract_id = await insert_document(
            conn, source='fixtures/contract.docx', doc_type='contract', content_hash='h1'
        )
        contract_ids = await insert_chunks(
            conn,
            contract_id,
            [
                ChunkRecord(
                    content='Раздел 5. Ответственность сторон. 5.1 ... 5.2 ...',
                    chunk_type='section',
                    ts_config='russian',
                    is_retrievable=False,
                ),
                ChunkRecord(
                    content='5.1 За просрочку поставки Поставщик уплачивает неустойку '
                    'в размере 0,1% от стоимости товара за каждый день.',
                    chunk_type='clause',
                    ts_config='russian',
                    embedding=PENALTY,
                    parent_index=0,
                    metadata={'clause': '5.1'},
                ),
                ChunkRecord(
                    content='5.2 Сроки передачи товара согласуются в спецификации.',
                    chunk_type='clause',
                    ts_config='russian',
                    embedding=DELIVERY,
                    parent_index=0,
                    metadata={'clause': '5.2'},
                ),
            ],
        )
        code_id = await insert_document(
            conn, source='fixtures/billing.py', doc_type='code', content_hash='h2'
        )
        code_ids = await insert_chunks(
            conn,
            code_id,
            [
                ChunkRecord(
                    content='def parse_invoice_total(rows): return sum(r.amount for r in rows)',
                    chunk_type='function',
                    ts_config='simple',
                    embedding=CODE,
                ),
                ChunkRecord(
                    content='| year | revenue |\n| 2024 | 100 |',
                    chunk_type='table_rows',
                    ts_config='english',
                    embedding=TABLE,
                ),
            ],
        )
    return Corpus(
        contract_id=contract_id,
        code_id=code_id,
        chunk_ids={
            'section': contract_ids[0],
            'penalty': contract_ids[1],
            'delivery': contract_ids[2],
            'code': code_ids[0],
            'table': code_ids[1],
        },
    )


async def test_fts_matches_russian_word_forms(db_pool: Pool, corpus: Corpus) -> None:
    hits = await fts_only(db_pool, query='неустойка за просрочку', top_n=5)

    assert [h.chunk_id for h in hits] == [corpus.chunk_ids['penalty']]
    assert hits[0].fts_rank == 1
    assert hits[0].vec_rank is None


async def test_fts_matches_code_identifier(db_pool: Pool, corpus: Corpus) -> None:
    hits = await fts_only(db_pool, query='parse_invoice_total', top_n=5)

    assert [h.chunk_id for h in hits] == [corpus.chunk_ids['code']]


async def test_vector_finds_paraphrase(db_pool: Pool, corpus: Corpus) -> None:
    # Запрос без общих слов с текстом, но близкий по «смыслу» к пункту о сроках.
    hits = await vector_only(db_pool, embedding=[0.1, 0.9, 0.0, 0.0], top_n=2)

    assert hits[0].chunk_id == corpus.chunk_ids['delivery']
    assert hits[0].vec_rank == 1
    assert hits[0].vec_distance is not None
    assert corpus.chunk_ids['section'] not in {h.chunk_id for h in hits}


async def test_hybrid_rrf_prefers_chunk_found_by_both_channels(
    db_pool: Pool, corpus: Corpus
) -> None:
    # Вектор ближе к пункту о сроках, но FTS находит только пункт о неустойке:
    # чанк из обоих каналов должен выйти первым.
    hits = await hybrid_search(
        db_pool,
        embedding=[0.6, 0.8, 0.0, 0.0],
        query='неустойка',
        top_n=10,
        vector_top_n=10,
        fts_top_n=10,
        rrf_k=60,
    )

    assert hits[0].chunk_id == corpus.chunk_ids['penalty']
    assert hits[0].vec_rank == 2
    assert hits[0].fts_rank == 1
    assert hits[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert hits[1].chunk_id == corpus.chunk_ids['delivery']
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


async def test_hybrid_filters_by_doc_type_and_metadata(db_pool: Pool, corpus: Corpus) -> None:
    async def search(
        doc_types: list[str] | None = None, metadata_filter: dict[str, str] | None = None
    ) -> list[SearchHit]:
        return await hybrid_search(
            db_pool,
            embedding=CODE,
            query='parse_invoice_total',
            top_n=10,
            vector_top_n=10,
            fts_top_n=10,
            doc_types=doc_types,
            metadata_filter=metadata_filter,
        )

    contract_hits = await search(doc_types=['contract'])
    clause_hits = await search(metadata_filter={'clause': '5.2'})

    assert {h.doc_type for h in contract_hits} == {'contract'}
    assert [h.chunk_id for h in clause_hits] == [corpus.chunk_ids['delivery']]


async def test_fetch_parents_returns_non_retrievable_parent(db_pool: Pool, corpus: Corpus) -> None:
    hits = await fts_only(db_pool, query='неустойка', top_n=1)
    parent_id = hits[0].parent_id
    assert parent_id == corpus.chunk_ids['section']

    parents = await fetch_parents(db_pool, [parent_id, parent_id])

    assert list(parents) == [parent_id]
    assert parents[parent_id].content.startswith('Раздел 5.')


async def test_delete_document_cascades(db_pool: Pool) -> None:
    async with db_pool.acquire() as conn, conn.transaction():
        doc_id = await insert_document(
            conn, source='fixtures/tmp.txt', doc_type='text', content_hash='h3'
        )
        chunk = ChunkRecord(content='уникальныйтермин', chunk_type='text', embedding=TABLE)
        await insert_chunks(conn, doc_id, [chunk])

    stored = await get_document_by_source(db_pool, 'fixtures/tmp.txt')
    assert stored is not None and stored.id == doc_id

    assert await delete_document(db_pool, doc_id)
    assert not await delete_document(db_pool, doc_id)
    assert await fts_only(db_pool, query='уникальныйтермин', top_n=5) == []
    assert await get_document_by_source(db_pool, 'fixtures/tmp.txt') is None


async def test_insert_chunks_rejects_forward_parent(db_pool: Pool, corpus: Corpus) -> None:
    async with db_pool.acquire() as conn:
        with pytest.raises(ValueError, match='parent_index'):
            await insert_chunks(
                conn,
                corpus.code_id,
                [ChunkRecord(content='x', chunk_type='text', embedding=TABLE, parent_index=0)],
            )


async def test_init_db_rejects_dim_above_hnsw_limit(db_pool: Pool) -> None:
    with pytest.raises(ValueError, match='halfvec'):
        await init_db(db_pool, 3072)
