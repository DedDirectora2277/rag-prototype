"""Адаптер AnythingLLM (self-hosted 1.18, single-user): ключ API, загрузка корпуса, поиск.

AnythingLLM подключается к тому же LiteLLM, что и наша система (Generic OpenAI для `chat` и
`embed`, задаётся переменными окружения контейнера). Контексты берутся через Developer API
(`/api/v1/workspace/{slug}/vector-search` — тот же поиск, что при чате с workspace), ответ
генерируется общим генератором стенда (`app.generation`), чтобы сравнение изолировало retrieval.
"""

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger('benchmarks.anythingllm')

# Форматы, которые collector AnythingLLM разбирает сам; исходники и rst загружаются как текст.
SUPPORTED = frozenset({'.txt', '.md', '.pdf', '.docx', '.xlsx', '.csv', '.html', '.pptx'})


@dataclass(slots=True)
class AnythingLLMConfig:
    """Параметры инстанса AnythingLLM и стенда."""

    base_url: str = 'http://localhost:3001'
    workspace_name: str = 'rag-bench'


async def generate_api_key(cfg: AnythingLLMConfig) -> str:
    """Создаёт ключ Developer API (в single-user режиме без пароля внутренний API открыт)."""
    async with httpx.AsyncClient(base_url=f'{cfg.base_url}/api', timeout=60) as http:
        response = await http.post('/system/generate-api-key')
        if response.status_code >= 400:
            raise RuntimeError(f'generate-api-key: {response.status_code} {response.text[:300]}')
        return str(response.json()['apiKey']['secret'])


class AnythingLLMClient:
    """Клиент Developer API (`/api/v1`, ключ в `Authorization: Bearer`)."""

    def __init__(self, cfg: AnythingLLMConfig, api_key: str) -> None:
        # Эмбеддинг документов идёт синхронно внутри запроса, поэтому таймаут большой.
        self.http = httpx.AsyncClient(
            base_url=f'{cfg.base_url}/api/v1',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=1800,
        )

    async def close(self) -> None:
        """Закрывает HTTP-клиент."""
        await self.http.aclose()

    async def call(self, method: str, path: str, **kwargs: Any) -> Any:
        """Произвольный вызов Developer API."""
        response = await self.http.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:500]}')
        return response.json() if response.content else None

    async def upload(self, data: bytes, name: str) -> str:
        """Загружает и разбирает файл (без эмбеддинга), возвращает `location` документа."""
        result = await self.call('POST', '/document/upload', files={'file': (name, data)})
        if not result.get('success') or not result.get('documents'):
            raise RuntimeError(f'upload {name}: {result.get("error")}')
        return str(result['documents'][0]['location'])

    async def embed(self, slug: str, locations: list[str]) -> None:
        """Добавляет документы в workspace: нарезка и эмбеддинг."""
        await self.call('POST', f'/workspace/{slug}/update-embeddings', json={'adds': locations})

    async def search(
        self, slug: str, query: str, top_n: int, score_threshold: float
    ) -> list[dict[str, Any]]:
        """Поиск по workspace: элементы с `text`, `metadata.title`, `score`."""
        result = await self.call(
            'POST',
            f'/workspace/{slug}/vector-search',
            json={'query': query, 'topN': top_n, 'scoreThreshold': score_threshold},
        )
        return list(result['results'])
