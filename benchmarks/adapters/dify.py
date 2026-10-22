"""Адаптер Dify (self-hosted 1.17): настройка через Console API, загрузка корпуса и retrieval.

Dify подключается к тому же LiteLLM, что и наша система (модели `chat`, `embed`, `rerank`
через плагин OpenAI-API-compatible). Контексты берутся через Knowledge API
(`/v1/datasets/{id}/retrieve`), ответ генерируется общим генератором стенда
(`app.generation`), чтобы сравнение изолировало retrieval.
"""

import asyncio
import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger('benchmarks.dify')

# Dify принимает не все расширения; исходники и rst загружаются как текст (содержимое то же).
SUPPORTED = frozenset(
    {'.txt', '.md', '.markdown', '.pdf', '.docx', '.xlsx', '.xls', '.csv', '.html'}
)
PROVIDER = 'langgenius/openai_api_compatible/openai_api_compatible'


@dataclass(slots=True)
class DifyConfig:
    """Параметры инстанса Dify и стенда."""

    base_url: str = 'http://localhost:8090'
    email: str = 'bench@example.com'
    password: str = 'Bench-pass-2026'
    # LiteLLM из контейнеров Dify (Docker Desktop пробрасывает хост как host.docker.internal).
    litellm_url: str = 'http://host.docker.internal:4000/v1'
    litellm_key: str = 'sk-rag-proto'
    dataset_name: str = 'rag-bench'


class DifyConsole:
    """Клиент Console API (сессия администратора через cookie + CSRF)."""

    def __init__(self, cfg: DifyConfig) -> None:
        self.cfg = cfg
        self.http = httpx.AsyncClient(base_url=f'{cfg.base_url}/console/api', timeout=120)

    async def close(self) -> None:
        """Закрывает HTTP-клиент."""
        await self.http.aclose()

    async def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        csrf = self.http.cookies.get('csrf_token')
        headers = {'X-CSRF-Token': csrf} if csrf else {}
        response = await self.http.request(method, path, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:500]}')
        return response.json() if response.content else None

    async def setup_and_login(self) -> None:
        """Создаёт администратора (если инстанс новый) и входит."""
        status = (await self.http.get('/setup')).json()
        if status.get('step') != 'finished':
            await self._call(
                'POST',
                '/setup',
                json={'email': self.cfg.email, 'name': 'bench', 'password': self.cfg.password},
            )
        encoded = base64.b64encode(self.cfg.password.encode()).decode()
        for password in (encoded, self.cfg.password):
            response = await self.http.post(
                '/login',
                json={'email': self.cfg.email, 'password': password, 'remember_me': True},
            )
            if response.status_code < 400 and response.json().get('result') == 'success':
                data = response.json().get('data') or {}
                if isinstance(data, dict) and data.get('access_token'):
                    self.http.headers['Authorization'] = f'Bearer {data["access_token"]}'
                return
        raise RuntimeError(f'вход в Dify не удался: {response.status_code} {response.text[:300]}')

    async def call(self, method: str, path: str, **kwargs: Any) -> Any:
        """Произвольный вызов Console API (для отладки и шагов настройки)."""
        return await self._call(method, path, **kwargs)


class DifyKnowledge:
    """Клиент Knowledge API (ключ датасета)."""

    def __init__(self, cfg: DifyConfig, api_key: str) -> None:
        self.http = httpx.AsyncClient(
            base_url=f'{cfg.base_url}/v1',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=300,
        )

    async def close(self) -> None:
        """Закрывает HTTP-клиент."""
        await self.http.aclose()

    async def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self.http.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:500]}')
        return response.json() if response.content else None

    async def upload(self, dataset_id: str, data: bytes, name: str, process: dict[str, Any]) -> str:
        """Загружает файл в датасет, возвращает batch индексации."""
        upload_name = name if Path(name).suffix.lower() in SUPPORTED else f'{name}.txt'
        files = {'file': (upload_name, data)}
        form = {'data': json.dumps(process)}
        result = await self._call(
            'POST', f'/datasets/{dataset_id}/document/create-by-file', files=files, data=form
        )
        return str(result['batch'])

    async def indexing_status(self, dataset_id: str, batch: str) -> list[dict[str, Any]]:
        """Статус индексации batch."""
        result = await self._call(
            'GET', f'/datasets/{dataset_id}/documents/{batch}/indexing-status'
        )
        return list(result['data'])

    async def retrieve(
        self, dataset_id: str, query: str, retrieval_model: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Поиск по датасету: записи с `segment.content`, `segment.document.name`, `score`."""
        result = await self._call(
            'POST',
            f'/datasets/{dataset_id}/retrieve',
            json={'query': query, 'retrieval_model': retrieval_model},
        )
        return list(result['records'])

    async def wait_indexed(self, dataset_id: str, batches: list[str], poll_s: float = 15) -> None:
        """Ждёт окончания индексации всех batch, логирует прогресс."""
        pending = set(batches)
        while pending:
            for batch in list(pending):
                statuses = await self.indexing_status(dataset_id, batch)
                states = {s['indexing_status'] for s in statuses}
                if states <= {'completed', 'error', 'paused'}:
                    for s in statuses:
                        if s['indexing_status'] == 'error':
                            logger.error('индексация %s: %s', s.get('id'), s.get('error'))
                    pending.discard(batch)
            logger.info('индексация: осталось %s из %s', len(pending), len(batches))
            if pending:
                await asyncio.sleep(poll_s)
