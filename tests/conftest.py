from collections.abc import AsyncIterator

import pytest

from app.config import Settings
from app.db.client import Pool, create_pool, init_db

# Маленькая размерность, чтобы тесты не зависели от реального эмбеддера.
TEST_EMBED_DIM = 4


@pytest.fixture(scope='session')
async def db_pool() -> AsyncIterator[Pool]:
    settings = Settings()
    try:
        pool = await create_pool(settings)
    except OSError as exc:
        pytest.skip(f'PostgreSQL недоступен ({settings.database_dsn}): {exc}')

    # Отдельная схема: тесты не трогают рабочие таблицы и могут менять размерность.
    await pool.execute('DROP SCHEMA IF EXISTS rag_test CASCADE; CREATE SCHEMA rag_test')
    await pool.close()

    settings = Settings(
        database_dsn=_with_search_path(settings.database_dsn, 'rag_test,public'),
        embed_dim=TEST_EMBED_DIM,
    )
    pool = await create_pool(settings)
    await init_db(pool, settings.embed_dim)
    try:
        yield pool
    finally:
        await pool.execute('DROP SCHEMA rag_test CASCADE')
        await pool.close()


def _with_search_path(dsn: str, search_path: str) -> str:
    # asyncpg передаёт неизвестные параметры DSN как server_settings.
    sep = '&' if '?' in dsn else '?'
    return f'{dsn}{sep}search_path={search_path.replace(",", "%2C")}'
