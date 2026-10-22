"""Нарезка таблиц: summary-чанк, группы строк с повторением шапки и таблица целиком как parent."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import PurePath
from typing import Any

from app.chunkers.base import Chunk, ParsedDocument, Table, count_tokens, detect_ts_config
from app.chunkers.common_text import CommonTextChunker

_UNITS = re.compile(
    r'(?:тыс|млн|млрд)\.?\s*(?:руб|долл|евро)\w*\.?|thousands?|millions?|billions?'
    r'|in\s+(?:thousands|millions|billions)|%',
    re.IGNORECASE,
)
_YEAR = re.compile(r'\b(?:19|20)\d{2}\b')
_NUMBER = re.compile(r'^[-−–+]?\(?[-−–]?[$€₽£]?\s*\d[\d\s  .,\']*\)?\s*(?:%|[$€₽£]|руб\.?|р\.)?$')
_SPACES = re.compile(r'[\s  \']')
_MAX_SUMMARY_KEYS = 30


def normalize_number(value: str) -> str | None:
    """Приводит запись числа к каноническому виду для полнотекстового поиска.

    Понимает пробелы-разделители разрядов, десятичную запятую, `1,234.5`,
    отрицательные числа в скобках, знаки валют и процентов.

    Args:
        value: Значение ячейки.

    Returns:
        Число без разделителей разрядов (`1234.5`, `-123`) или `None`, если это не число.
    """
    text = value.strip()
    if not text or not _NUMBER.match(text):
        return None
    negative = text.startswith(('(', '-', '−', '–')) or '(-' in text
    digits = re.sub(r'[^\d.,\s  \']', '', text)
    digits = _SPACES.sub('', digits)
    if ',' in digits and '.' in digits:
        # Последний из разделителей — десятичный.
        decimal_sep = ',' if digits.rfind(',') > digits.rfind('.') else '.'
        thousands_sep = '.' if decimal_sep == ',' else ','
        digits = digits.replace(thousands_sep, '').replace(decimal_sep, '.')
    elif ',' in digits:
        # «1,234» и «1,234,567» — разряды (англоязычная отчётность), «12,5» — десятичная запятая.
        digits = (
            digits.replace(',', '')
            if re.fullmatch(r'\d{1,3}(?:,\d{3})+', digits)
            else digits.replace(',', '.')
        )
    elif digits.count('.') > 1:
        # «1.234.567» — разряды; «5.2.1» — номер пункта, а не число.
        if not re.fullmatch(r'\d{1,3}(?:\.\d{3})+', digits):
            return None
        digits = digits.replace('.', '')
    try:
        number = Decimal(digits)
    except InvalidOperation:
        return None
    if negative:
        number = -number
    return format(number.normalize(), 'f')


def _cell(value: str) -> str:
    return ' '.join(value.replace('|', '\\|').split())


def to_markdown(header: list[str], rows: Iterable[list[str]]) -> str:
    """Сериализует таблицу в markdown.

    Args:
        header: Названия колонок.
        rows: Строки (дополняются пустыми ячейками до ширины шапки).

    Returns:
        Таблица в формате markdown.
    """
    lines = [
        '| ' + ' | '.join(_cell(h) for h in header) + ' |',
        '|' + '---|' * len(header),
    ]
    for row in rows:
        cells = [*row, *[''] * (len(header) - len(row))]
        lines.append('| ' + ' | '.join(_cell(c) for c in cells) + ' |')
    return '\n'.join(lines)


def _numbers_line(rows: Iterable[list[str]]) -> str:
    """Строка с нормализованными числами, если их запись отличается от исходной."""
    seen: list[str] = []
    for row in rows:
        for cell in row:
            normalized = normalize_number(cell)
            if normalized is not None and normalized != cell.strip() and normalized not in seen:
                seen.append(normalized)
    return f'\nЧисла: {" ".join(seen)}' if seen else ''


def _header(table: Table) -> list[str]:
    width = max([len(table.header), *(len(row) for row in table.rows)], default=0)
    header = [h.strip() or f'col{i + 1}' for i, h in enumerate(table.header)]
    return header + [f'col{i + 1}' for i in range(len(header), width)]


def _units_and_period(table: Table, header: list[str]) -> tuple[str | None, list[str]]:
    probe = ' '.join([table.name or '', *header, str(table.metadata.get('sheet', ''))])
    units = table.metadata.get('units')
    if units is None and (m := _UNITS.search(probe)):
        units = m.group(0)
    period = table.metadata.get('period')
    years = [str(period)] if period else sorted(set(_YEAR.findall(probe)))
    return units, years


@dataclass(frozen=True, slots=True)
class TableChunker:
    """Чанкер таблиц и финансовых отчётов.

    Attributes:
        rows_per_chunk: Максимум строк в группе.
        max_tokens: Лимит размера группы строк в токенах.
        parent_max_tokens: Таблица больше этого не сохраняется целиком как parent.
        text_max_tokens: Лимит для текста документа вокруг таблиц.
        text_overlap_tokens: Перекрытие для текста вокруг таблиц.
    """

    rows_per_chunk: int = 20
    max_tokens: int = 512
    parent_max_tokens: int = 4000
    text_max_tokens: int = 512
    text_overlap_tokens: int = 64

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        """Нарезает таблицы документа (и текст вокруг них, если есть).

        Args:
            doc: Разобранный документ с `doc.tables`.

        Returns:
            Для каждой таблицы — parent с детьми (summary и группы строк), либо,
            если таблица слишком большая, сами дети без parent.
        """
        chunks = CommonTextChunker(self.text_max_tokens, self.text_overlap_tokens).chunk(doc)
        for index, table in enumerate(doc.tables):
            chunks.extend(self._table(doc, index, table))
        return chunks

    def _table(self, doc: ParsedDocument, index: int, table: Table) -> list[Chunk]:
        header = _header(table)
        name = table.name or f'{PurePath(doc.source).name}, таблица {index + 1}'
        ts_config = detect_ts_config(' '.join([name, *header, *(c for r in table.rows for c in r)]))
        meta: dict[str, Any] = {**table.metadata, 'table_index': index, 'table_name': name}

        children = [
            self._summary(table, name, header, meta),
            *self._row_groups(name, header, table.rows, meta),
        ]
        for child in children:
            child.ts_config = ts_config

        full = f'{name}\n\n{to_markdown(header, table.rows)}'
        if count_tokens(full) > self.parent_max_tokens:
            return children
        return [
            Chunk(
                content=full,
                chunk_type='table',
                metadata=meta,
                children=children,
                ts_config=ts_config,
            )
        ]

    def _summary(self, table: Table, name: str, header: list[str], meta: dict[str, Any]) -> Chunk:
        units, years = _units_and_period(table, header)
        lines = [f'Таблица: {name}']
        if sheet := table.metadata.get('sheet'):
            lines.append(f'Лист: {sheet}')
        if units:
            lines.append(f'Единицы: {units}')
        if years:
            lines.append(f'Период: {", ".join(years)}')
        lines.append(f'Колонки: {", ".join(header)}')
        lines.append(f'Строк: {len(table.rows)}')

        keys = [row[0].strip() for row in table.rows if row and row[0].strip()]
        shown: list[str] = []
        for key in keys[:_MAX_SUMMARY_KEYS]:
            candidate = '\n'.join([*lines, f'{header[0]}: {", ".join([*shown, key])}'])
            if count_tokens(candidate) > self.max_tokens:
                break
            shown.append(key)
        if shown:
            more = ', …' if len(shown) < len(keys) else ''
            lines.append(f'{header[0]}: {", ".join(shown)}{more}')

        summary_meta = {**meta, 'rows': len(table.rows), 'columns': header}
        if units:
            summary_meta['units'] = units
        if years:
            summary_meta['period'] = years
        return Chunk(content='\n'.join(lines), chunk_type='table_summary', metadata=summary_meta)

    def _row_groups(
        self, name: str, header: list[str], rows: list[list[str]], meta: dict[str, Any]
    ) -> list[Chunk]:
        """Группы строк с шапкой: не больше `rows_per_chunk` строк и `max_tokens` токенов."""

        def render(group: list[list[str]]) -> str:
            return f'{name}\n\n{to_markdown(header, group)}{_numbers_line(group)}'

        chunks: list[Chunk] = []
        start = 0
        while start < len(rows):
            end = start + 1  # одна строка берётся всегда, даже если не влезает
            while (
                end < len(rows)
                and end - start < self.rows_per_chunk
                and count_tokens(render(rows[start : end + 1])) <= self.max_tokens
            ):
                end += 1
            chunks.append(
                Chunk(
                    content=render(rows[start:end]),
                    chunk_type='table_rows',
                    metadata={**meta, 'row_start': start + 1, 'row_end': end},
                )
            )
            start = end
        return chunks
