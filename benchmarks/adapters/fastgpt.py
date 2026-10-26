"""Адаптер FastGPT (self-hosted 4.17): вход root, настройка моделей, загрузка корпуса, поиск.

FastGPT подключается к тому же LiteLLM, что и наша система: модели `chat`, `embed`, `rerank`
заводятся как системные с custom request URL (в обход каналов AI Proxy). Контексты берутся
через `/api/core/dataset/searchTest` (тот же поиск, что у узла «Поиск по базе знаний»), ответ
генерируется общим генератором стенда (`app.generation`), чтобы сравнение изолировало retrieval.
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger('benchmarks.fastgpt')

# Форматы, которые FastGPT разбирает сам; исходники и rst загружаются как текст.
SUPPORTED = frozenset({'.txt', '.md', '.pdf', '.docx', '.html', '.csv', '.xlsx', '.pptx'})


@dataclass(slots=True)
class FastGPTConfig:
    """Параметры инстанса FastGPT и стенда."""

    base_url: str = 'http://localhost:3000'
    username: str = 'root'
    password: str = '1234'
    # LiteLLM из контейнеров FastGPT (Docker Desktop пробрасывает хост как host.docker.internal).
    litellm_url: str = 'http://host.docker.internal:4000/v1'
    litellm_key: str = 'sk-rag-proto'
    dataset_name: str = 'rag-bench'


class FastGPTClient:
    """Клиент внутреннего API FastGPT от имени root (cookie-сессия)."""

    def __init__(self, cfg: FastGPTConfig) -> None:
        self.cfg = cfg
        # Без заголовка `fastgpt-web-request` API отвечает 403 csrf_invalid.
        self.http = httpx.AsyncClient(
            base_url=f'{cfg.base_url}/api', headers={'fastgpt-web-request': '1'}, timeout=300
        )

    async def close(self) -> None:
        """Закрывает HTTP-клиент."""
        await self.http.aclose()

    async def call(self, method: str, path: str, **kwargs: Any) -> Any:
        """Вызов API: возвращает `data` из ответа `{code, message, data}`."""
        response = await self.http.request(method, path, **kwargs)
        body = response.json() if response.content else {}
        if response.status_code >= 400 or body.get('code', 200) != 200:
            raise RuntimeError(f'{method} {path}: {response.status_code} {response.text[:500]}')
        return body.get('data')

    async def login(self) -> None:
        """Входит под root: одноразовый код preLogin + SHA-256 пароля."""
        pre = await self.call(
            'GET', '/support/user/account/preLogin', params={'username': self.cfg.username}
        )
        await self.call(
            'POST',
            '/support/user/account/loginByPassword',
            json={
                'username': self.cfg.username,
                'password': hashlib.sha256(self.cfg.password.encode()).hexdigest(),
                'code': pre['code'],
            },
        )

    async def upload(self, dataset_id: str, data: bytes, name: str) -> str:
        """Создаёт коллекцию из файла с разбиением FastGPT по умолчанию, возвращает её id."""
        meta = {'datasetId': dataset_id, 'trainingType': 'chunk', 'chunkSettingMode': 'auto'}
        result = await self.call(
            'POST',
            '/core/dataset/collection/create/localFile',
            files={'file': (name, data)},
            data={'data': json.dumps(meta)},
        )
        return str(result['collectionId'])

    async def collections(self, dataset_id: str) -> list[dict[str, Any]]:
        """Все коллекции датасета (с `trainingAmount` — сколько данных ещё в очереди)."""
        items: list[dict[str, Any]] = []
        while True:
            page = await self.call(
                'POST',
                '/core/dataset/collection/listV2',
                json={'datasetId': dataset_id, 'offset': len(items), 'pageSize': 100},
            )
            items += page['list']
            if len(items) >= page['total'] or not page['list']:
                return items

    async def wait_trained(self, dataset_id: str, poll_s: float = 15) -> None:
        """Ждёт, пока у всех коллекций опустеет очередь обучения, логирует прогресс."""
        while True:
            pending = [c for c in await self.collections(dataset_id) if c.get('trainingAmount')]
            left = sum(int(c['trainingAmount']) for c in pending)
            logger.info('индексация: коллекций в очереди %s, фрагментов %s', len(pending), left)
            if not pending:
                return
            await asyncio.sleep(poll_s)

    async def search(self, dataset_id: str, query: str, params: dict[str, Any]) -> list[Any]:
        """Поиск по датасету: элементы с `q`, `a`, `sourceName`, `score`."""
        result = await self.call(
            'POST',
            '/core/dataset/searchTest',
            json={'datasetId': dataset_id, 'text': query, **params},
        )
        return list(result['list'])
