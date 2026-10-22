"""Cross-Encoder реранкер через Cohere-совместимый эндпоинт LiteLLM `/rerank`."""

import logging
from collections.abc import Sequence

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class Reranker:
    """Клиент `/rerank` LiteLLM (бэкенд — TEI с `bge-reranker-v2-m3`).

    Args:
        client: HTTP-клиент с `base_url` LiteLLM и заголовком авторизации.
        model: Алиас модели реранкера в LiteLLM.
    """

    def __init__(self, client: httpx.AsyncClient, model: str) -> None:
        self._client = client
        self._model = model

    @staticmethod
    def make_client(settings: Settings, timeout: float = 300.0) -> httpx.AsyncClient:
        """Создаёт HTTP-клиент для LiteLLM.

        Таймаут большой: на CPU кросс-энкодер обрабатывает 50 кандидатов минутами.

        Args:
            settings: Настройки приложения.
            timeout: Таймаут запроса в секундах.

        Returns:
            HTTP-клиент; закрывает его вызывающий код.
        """
        return httpx.AsyncClient(
            base_url=settings.litellm_url,
            headers={'Authorization': f'Bearer {settings.litellm_api_key}'},
            timeout=timeout,
        )

    async def rerank(
        self, query: str, docs: Sequence[str], top_n: int | None = None
    ) -> list[tuple[int, float]] | None:
        """Переранжирует документы по релевантности запросу.

        Args:
            query: Запрос.
            docs: Тексты кандидатов.
            top_n: Сколько лучших вернуть; `None` — все.

        Returns:
            Пары `(индекс в docs, скор)` по убыванию скора, либо `None`, если
            реранкер недоступен — тогда вызывающий код сохраняет исходный порядок.
        """
        if not docs:
            return []
        try:
            response = await self._client.post(
                '/rerank',
                json={
                    'model': self._model,
                    'query': query,
                    'documents': list(docs),
                    'top_n': top_n or len(docs),
                },
            )
            response.raise_for_status()
            results = response.json()['results']
            ranked = [(int(r['index']), float(r['relevance_score'])) for r in results]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            logger.warning('реранкер недоступен, оставляю порядок RRF: %r', exc)
            return None
        ranked.sort(key=lambda pair: pair[1], reverse=True)
        # LiteLLM не передаёт top_n в TEI и возвращает все документы — режем сами.
        return ranked[:top_n] if top_n is not None else ranked
