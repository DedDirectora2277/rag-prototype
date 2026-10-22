"""Общий контракт чанкеров: входной документ, дерево чанков и его сплющивание для БД."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Literal, Protocol

import tiktoken

from app.db.client import ChunkRecord

TsConfig = Literal['russian', 'english', 'simple']

# Доля кириллицы среди букв, начиная с которой текст считается русским.
_CYRILLIC_THRESHOLD = 0.3


@dataclass(frozen=True, slots=True)
class Table:
    """Таблица, извлечённая парсером.

    Attributes:
        name: Название таблицы (заголовок, имя листа), если известно.
        header: Названия колонок.
        rows: Строки таблицы; ячейки уже приведены к строкам.
        metadata: Лист, единицы измерения (`units`), период (`period`) и т.п.
    """

    name: str | None
    header: list[str]
    rows: list[list[str]]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Документ после парсинга, вход для чанкера.

    Attributes:
        source: Путь или URI документа.
        title: Заголовок документа, если известен.
        text: Текст документа (для таблиц — текст вокруг них, может быть пустым).
        tables: Таблицы документа.
        language: Язык исходного кода для tree-sitter (`python`, `go`, ...).
        metadata: Произвольные метаданные документа.
    """

    source: str
    title: str | None = None
    text: str = ''
    tables: list[Table] = field(default_factory=list)
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Chunk:
    """Узел дерева чанков.

    Чанк с детьми — parent: в поиск не попадает, но отдаётся при parent-expansion.

    Attributes:
        content: Текст чанка (то, что эмбеддится и индексируется FTS).
        chunk_type: Тип чанка (`text`, `clause`, `function`, `table_rows`, ...).
        metadata: Метаданные чанка.
        children: Дочерние чанки.
        ts_config: Конфигурация FTS; `None` — определить по тексту.
    """

    content: str
    chunk_type: str
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list['Chunk'] = field(default_factory=list)
    ts_config: TsConfig | None = None

    @property
    def is_retrievable(self) -> bool:
        """Участвует ли чанк в поиске (parent-чанки — нет)."""
        return not self.children


class Chunker(Protocol):
    """Чанкер превращает разобранный документ в дерево чанков."""

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        """Нарезает документ на чанки.

        Args:
            doc: Разобранный документ.

        Returns:
            Чанки верхнего уровня (с детьми, если есть иерархия).
        """
        ...


@lru_cache
def get_encoding() -> tiktoken.Encoding:
    """Возвращает закешированный токенизатор `cl100k_base`."""
    return tiktoken.get_encoding('cl100k_base')


def count_tokens(text: str) -> int:
    """Считает токены в тексте.

    Это приближение: эмбеддер bge-m3 использует токенизатор XLM-R, а здесь
    `cl100k_base`. Для лимитов размера чанков точности достаточно.

    Args:
        text: Текст.

    Returns:
        Число токенов `cl100k_base`.
    """
    return len(get_encoding().encode(text, disallowed_special=()))


def detect_ts_config(text: str) -> TsConfig:
    """Выбирает конфигурацию FTS по доле кириллицы среди букв.

    Args:
        text: Текст.

    Returns:
        `russian` или `english`.
    """
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 'english'
    cyrillic = sum(1 for ch in letters if 'а' <= ch.lower() <= 'я' or ch in 'ёЁ')
    return 'russian' if cyrillic / len(letters) >= _CYRILLIC_THRESHOLD else 'english'


def flatten(chunks: Sequence[Chunk], ts_config: TsConfig | None = None) -> list[ChunkRecord]:
    """Сплющивает дерево чанков в список для `insert_chunks`.

    Обход в глубину (pre-order), поэтому parent всегда стоит раньше детей.
    Эмбеддинги не заполняются: их добавит ingest.

    Args:
        chunks: Чанки верхнего уровня.
        ts_config: Конфигурация FTS по умолчанию; если `None` и у чанка она не
            задана, определяется по тексту чанка.

    Returns:
        Записи чанков с проставленными `parent_index` и `is_retrievable`.
    """
    records: list[ChunkRecord] = []

    def visit(chunk: Chunk, parent_index: int | None) -> None:
        index = len(records)
        records.append(
            ChunkRecord(
                content=chunk.content,
                chunk_type=chunk.chunk_type,
                ts_config=chunk.ts_config or ts_config or detect_ts_config(chunk.content),
                is_retrievable=chunk.is_retrievable,
                parent_index=parent_index,
                metadata=chunk.metadata,
            )
        )
        for child in chunk.children:
            visit(child, index)

    for chunk in chunks:
        visit(chunk, None)
    return records
