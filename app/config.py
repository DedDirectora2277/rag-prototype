from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ChunkerMode = Literal['naive', 'domain']


class Settings(BaseSettings):
    """Настройки прототипа; читаются из окружения и `.env` с префиксом `RAG_`.

    Флаги `use_fts`, `use_rerank`, `use_parent_expansion` и `chunker_mode`
    нужны для ablation-экспериментов.
    """

    model_config = SettingsConfigDict(env_prefix='RAG_', env_file='.env', extra='ignore')

    database_dsn: str = 'postgresql://rag:rag@localhost:5432/rag'
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10

    litellm_url: str = 'http://localhost:4000'
    litellm_api_key: str = 'sk-rag-proto'
    chat_model: str = 'chat'
    judge_model: str = 'judge'
    embed_model: str = 'embed'
    rerank_model: str = 'rerank'
    embed_dim: int = 1024  # BAAI/bge-m3
    embed_batch_size: int = 64
    embed_concurrency: int = 4

    vector_top_n: int = 50
    fts_top_n: int = 50
    hybrid_top_n: int = 50
    rrf_k: int = 60
    rerank_top_n: int = 8

    use_fts: bool = True
    use_rerank: bool = True
    use_parent_expansion: bool = True
    chunker_mode: ChunkerMode = 'domain'


@lru_cache
def get_settings() -> Settings:
    """Возвращает закешированный экземпляр настроек."""
    return Settings()
