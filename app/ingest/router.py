"""Выбор домена документа (`doc_type`) и чанкера по расширению и эвристикам текста."""

import re
from dataclasses import replace
from pathlib import PurePath
from typing import Literal

from app.chunkers.base import Chunk, ParsedDocument, count_tokens
from app.chunkers.code_ast import CodeAstChunker
from app.chunkers.common_text import CommonTextChunker, MarkdownChunker, NaiveChunker
from app.chunkers.hierarchical import HierarchicalChunker
from app.chunkers.tables import TableChunker
from app.config import Settings
from app.ingest.parsers import MARKUP_EXTENSIONS, TABLE_EXTENSIONS

DocType = Literal['contract', 'code', 'docs', 'table', 'text']
DOC_TYPES: tuple[DocType, ...] = ('contract', 'code', 'docs', 'table', 'text')

_LEGAL_HEADING = re.compile(
    r'^\s*(?:Раздел|Глава|Статья|Article|Section)\s+[\dIVXLC]+\b', re.IGNORECASE | re.MULTILINE
)
_CLAUSE = re.compile(r'^\s*\d{1,3}\.\d{1,3}\.?\s+\S', re.MULTILINE)
_LEGAL_TERMS = re.compile(
    r'договор|соглашени|контракт|закон|кодекс|постановлени|именуем|'
    r'\bagreement\b|\bcontract\b|hereinafter|\bparties\b|\blicens',
    re.IGNORECASE,
)
# Пороги эвристики договора: сколько структурных признаков достаточно.
_MIN_HEADINGS = 2
_MIN_CLAUSES = 5
_MIN_HEADINGS_WITHOUT_TERMS = 3


def looks_like_legal(text: str) -> bool:
    """Похож ли текст на договор или нормативный акт.

    Нужна структура (заголовки «Статья N»/«Раздел N» или пункты «5.2») и
    юридическая лексика; закон с тремя и более статьями проходит и без лексики.

    Args:
        text: Текст документа.

    Returns:
        `True`, если текст стоит резать иерархическим чанкером.
    """
    headings = len(_LEGAL_HEADING.findall(text))
    if headings >= _MIN_HEADINGS_WITHOUT_TERMS:
        return True
    structured = headings >= _MIN_HEADINGS or len(_CLAUSE.findall(text)) >= _MIN_CLAUSES
    return structured and _LEGAL_TERMS.search(text[:20000]) is not None


def detect_doc_type(doc: ParsedDocument) -> DocType:
    """Определяет домен документа.

    Args:
        doc: Разобранный документ (`metadata['extension']` выставляет парсер).

    Returns:
        `code`, `table`, `docs`, `contract` или `text`.
    """
    suffix = doc.metadata.get('extension') or PurePath(doc.source).suffix.lower()
    if doc.language is not None:
        return 'code'
    if suffix in TABLE_EXTENSIONS:
        return 'table'
    if suffix in MARKUP_EXTENSIONS:
        return 'docs'
    if looks_like_legal(doc.text):
        return 'contract'
    if doc.tables:
        # PDF/DOCX-отчёт: если таблиц по объёму не меньше текста — это табличный документ.
        table_tokens = sum(
            count_tokens(' '.join(cell for row in [t.header, *t.rows] for cell in row))
            for t in doc.tables
        )
        if table_tokens >= count_tokens(doc.text) // 2:
            return 'table'
    return 'text'


def chunk_document(doc: ParsedDocument, doc_type: DocType, settings: Settings) -> list[Chunk]:
    """Нарезает документ чанкером, соответствующим домену и `settings.chunker_mode`.

    В режиме `naive` все документы режутся фиксированным окном (baseline для ablation).

    Args:
        doc: Разобранный документ.
        doc_type: Домен документа.
        settings: Настройки (размеры чанков и режим чанкинга).

    Returns:
        Дерево чанков.
    """
    max_tokens = settings.chunk_max_tokens
    overlap = settings.chunk_overlap_tokens
    if settings.chunker_mode == 'naive':
        return NaiveChunker(settings.naive_window_tokens, overlap).chunk(doc)

    tables = TableChunker(
        rows_per_chunk=settings.table_rows_per_chunk,
        max_tokens=max_tokens,
        parent_max_tokens=settings.table_parent_max_tokens,
        text_max_tokens=max_tokens,
        text_overlap_tokens=overlap,
    )
    match doc_type:
        case 'code':
            return CodeAstChunker(max_tokens).chunk(doc)
        case 'docs':
            return MarkdownChunker(max_tokens, overlap).chunk(doc)
        case 'table':
            return tables.chunk(doc)
        case 'contract':
            chunks = HierarchicalChunker(max_tokens, overlap).chunk(doc)
            if doc.tables:
                # Таблицы договора (спецификации, графики платежей) — отдельными чанками.
                chunks += tables.chunk(replace(doc, text=''))
            return chunks
        case 'text':
            chunks = CommonTextChunker(max_tokens, overlap).chunk(doc)
            if doc.tables:
                chunks += tables.chunk(replace(doc, text=''))
            return chunks
