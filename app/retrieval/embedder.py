"""Эмбеддинги через LiteLLM (OpenAI-совместимый `/v1/embeddings`)."""

import asyncio
from collections.abc import Sequence

from openai import AsyncOpenAI

from app.config import Settings


class Embedder:
    """Тонкая обёртка над `embeddings.create`: батчи и ограничение параллельности.

    Args:
        client: Клиент OpenAI, смотрящий на LiteLLM.
        model: Алиас модели эмбеддингов в LiteLLM.
        dim: Ожидаемая размерность (проверяется, чтобы не записать в БД чужие векторы).
        batch_size: Сколько текстов отправлять в одном запросе.
        concurrency: Сколько запросов выполнять одновременно.
    """

    def __init__(
        self, client: AsyncOpenAI, model: str, dim: int, batch_size: int = 64, concurrency: int = 4
    ) -> None:
        self._client = client
        self._model = model
        self._dim = dim
        self._batch_size = batch_size
        self._semaphore = asyncio.Semaphore(concurrency)

    @classmethod
    def from_settings(cls, client: AsyncOpenAI, settings: Settings) -> 'Embedder':
        """Создаёт эмбеддер с параметрами из настроек.

        Args:
            client: Клиент OpenAI, смотрящий на LiteLLM.
            settings: Настройки приложения.

        Returns:
            Эмбеддер.
        """
        return cls(
            client,
            settings.embed_model,
            settings.embed_dim,
            settings.embed_batch_size,
            settings.embed_concurrency,
        )

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Считает эмбеддинги текстов с сохранением порядка.

        Args:
            texts: Тексты.

        Returns:
            Векторы в порядке `texts`.

        Raises:
            ValueError: Если размерность ответа не совпадает с ожидаемой.
        """
        batches = [
            list(texts[i : i + self._batch_size]) for i in range(0, len(texts), self._batch_size)
        ]
        results = await asyncio.gather(*(self._embed_batch(batch) for batch in batches))
        return [vector for batch in results for vector in batch]

    async def embed_query(self, query: str) -> list[float]:
        """Считает эмбеддинг поискового запроса.

        bge-m3 не требует инструкции-префикса для запросов, поэтому запрос
        эмбеддится так же, как документ.

        Args:
            query: Текст запроса.

        Returns:
            Вектор запроса.
        """
        return (await self._embed_batch([query]))[0]

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        async with self._semaphore:
            response = await self._client.embeddings.create(model=self._model, input=texts)
        # Порядок в ответе не гарантирован спецификацией — сортируем по index.
        vectors = [item.embedding for item in sorted(response.data, key=lambda d: d.index)]
        if len(vectors) != len(texts):
            raise ValueError(f'эмбеддер вернул {len(vectors)} векторов на {len(texts)} текстов')
        if vectors and len(vectors[0]) != self._dim:
            raise ValueError(f'размерность эмбеддинга {len(vectors[0])}, ожидалась {self._dim}')
        return vectors
