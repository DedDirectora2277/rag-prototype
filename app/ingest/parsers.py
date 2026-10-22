"""Парсинг файлов в `ParsedDocument`: текст, исходный код, DOCX, PDF, XLSX и CSV."""

import csv
import io
import logging
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date, datetime
from pathlib import PurePath
from typing import Any

import docx
import pdfplumber
import tree_sitter_language_pack as tslp
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from openpyxl import load_workbook

from app.chunkers.base import ParsedDocument, Table

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = frozenset({'.txt', '.text', '.log'})
MARKUP_EXTENSIONS = frozenset({'.md', '.markdown', '.rst'})
TABLE_EXTENSIONS = frozenset({'.csv', '.tsv', '.xlsx', '.xlsm'})
# Языки, которые tree-sitter распознаёт по расширению, но которые не являются кодом.
_NON_CODE_LANGUAGES = frozenset({'markdown', 'rst', 'vimdoc', 'csv', 'tsv'})
# Кодировки текстовых файлов в порядке попыток; cp1251 — частый случай для русских документов.
_ENCODINGS = ('utf-8-sig', 'cp1251')


class UnsupportedFormatError(ValueError):
    """Формат файла не поддерживается парсером."""


def code_language(filename: str) -> str | None:
    """Определяет язык исходного кода по имени файла.

    Args:
        filename: Имя или путь файла.

    Returns:
        Имя грамматики tree-sitter или `None`, если это не исходный код.
    """
    if PurePath(filename).suffix.lower() in TEXT_EXTENSIONS | MARKUP_EXTENSIONS:
        return None
    language = tslp.detect_language_from_path(filename)
    return None if language in _NON_CODE_LANGUAGES else language


def is_supported(filename: str) -> bool:
    """Поддерживается ли файл парсером (по расширению).

    Args:
        filename: Имя или путь файла.

    Returns:
        `True`, если файл можно разобрать.
    """
    suffix = PurePath(filename).suffix.lower()
    return (
        suffix in _PARSERS
        or suffix in TEXT_EXTENSIONS | MARKUP_EXTENSIONS
        or code_language(filename) is not None
    )


def parse_bytes(data: bytes, filename: str, source: str | None = None) -> ParsedDocument:
    """Разбирает содержимое файла в `ParsedDocument`.

    Args:
        data: Содержимое файла.
        filename: Имя файла; по расширению выбирается парсер.
        source: Источник документа; по умолчанию — `filename`.

    Returns:
        Разобранный документ.

    Raises:
        UnsupportedFormatError: Если формат не поддерживается.
    """
    source = source or filename
    suffix = PurePath(filename).suffix.lower()
    metadata: dict[str, Any] = {'filename': PurePath(filename).name, 'extension': suffix}

    parser = _PARSERS.get(suffix)
    if parser is not None:
        doc = parser(data, source)
        return ParsedDocument(
            source=doc.source,
            title=doc.title,
            text=doc.text,
            tables=doc.tables,
            metadata={**metadata, **doc.metadata},
        )

    language = code_language(filename)
    if suffix in TEXT_EXTENSIONS | MARKUP_EXTENSIONS or language is not None:
        return ParsedDocument(
            source=source, text=decode_text(data), language=language, metadata=metadata
        )
    raise UnsupportedFormatError(f'неподдерживаемый формат файла: {filename}')


def decode_text(data: bytes) -> str:
    """Декодирует текстовый файл: UTF-8, затем cp1251, иначе UTF-8 с заменой символов.

    Args:
        data: Содержимое файла.

    Returns:
        Текст с нормализованными переводами строк.
    """
    for encoding in _ENCODINGS:
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode('utf-8', errors='replace')
    return text.replace('\r\n', '\n').replace('\r', '\n')


def _cell_text(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == datetime.min.time() else str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return ' '.join(str(value).split())


def _make_table(name: str | None, rows: Iterable[Iterable[Any]], **metadata: Any) -> Table | None:
    """Чистит сырые строки (пустые строки и колонки) и делает `Table` с шапкой из первой строки."""
    cleaned = [[_cell_text(v) for v in row] for row in rows]
    cleaned = [row for row in cleaned if any(row)]
    if not cleaned:
        return None
    width = max(len(row) for row in cleaned)
    cleaned = [row + [''] * (width - len(row)) for row in cleaned]
    keep = [j for j in range(width) if any(row[j] for row in cleaned)]
    cleaned = [[row[j] for j in keep] for row in cleaned]
    return Table(name=name, header=cleaned[0], rows=cleaned[1:], metadata=metadata)


def _parse_csv(data: bytes, source: str) -> ParsedDocument:
    text = decode_text(data)
    if PurePath(source).suffix.lower() == '.tsv':
        delimiter = '\t'
    else:
        try:
            delimiter = csv.Sniffer().sniff(text[:4096], delimiters=',;\t').delimiter
        except csv.Error:
            delimiter = ','
    table = _make_table(None, csv.reader(io.StringIO(text), delimiter=delimiter))
    return ParsedDocument(source=source, tables=[table] if table else [])


def _parse_xlsx(data: bytes, source: str) -> ParsedDocument:
    # data_only: значения формул из кеша файла, а не сами формулы.
    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        tables = [
            table
            for sheet in workbook.worksheets
            if (
                table := _make_table(
                    sheet.title, sheet.iter_rows(values_only=True), sheet=sheet.title
                )
            )
        ]
    finally:
        workbook.close()
    # Одиночный лист с именем по умолчанию ничего не говорит о таблице — имя даст чанкер.
    if len(tables) == 1 and tables[0].name in {'Sheet', 'Sheet1', 'Лист1'}:
        tables = [Table(None, tables[0].header, tables[0].rows, tables[0].metadata)]
    return ParsedDocument(source=source, tables=tables)


def _numbering(paragraph: Paragraph) -> tuple[str, int] | None:
    """Возвращает `(numId, уровень)` автонумерации абзаца (из самого абзаца или его стиля)."""
    for element in (paragraph._p, getattr(paragraph.style, 'element', None)):
        ppr = element.find(qn('w:pPr')) if element is not None else None
        num_pr = ppr.find(qn('w:numPr')) if ppr is not None else None
        if num_pr is None:
            continue
        num_id = num_pr.find(qn('w:numId'))
        ilvl = num_pr.find(qn('w:ilvl'))
        if num_id is None or num_id.get(qn('w:val')) == '0':
            return None
        level = int(ilvl.get(qn('w:val'))) if ilvl is not None else 0
        return num_id.get(qn('w:val')), level
    return None


def _parse_docx(data: bytes, source: str) -> ParsedDocument:
    document = docx.Document(io.BytesIO(data))
    # Автонумерация Word («1.2.») не входит в paragraph.text, а от неё зависит разбор
    # структуры договора. Восстанавливаем номера счётчиками по numId и уровню; формат
    # из numbering.xml (буквы, римские цифры) не учитывается — всегда «1.2.3.».
    counters: dict[str, list[int]] = defaultdict(lambda: [0] * 9)
    lines = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        numbering = _numbering(paragraph)
        if text and numbering is not None:
            num_id, level = numbering
            level = min(level, 8)
            counter = counters[num_id]
            counter[level] += 1
            counter[level + 1 :] = [0] * (8 - level)
            number = '.'.join(str(n) for n in counter[: level + 1] if n) or '1'
            text = f'{number}. {text}' if level == 0 else f'{number} {text}'
        lines.append(text)

    tables = [
        table
        for i, t in enumerate(document.tables)
        if (
            table := _make_table(
                None, ([cell.text for cell in row.cells] for row in t.rows), index=i
            )
        )
    ]
    title = (document.core_properties.title or '').strip() or None
    return ParsedDocument(source=source, title=title, text='\n'.join(lines), tables=tables)


def _parse_pdf(data: bytes, source: str) -> ParsedDocument:
    pages = []
    tables = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        title = (pdf.metadata.get('Title') or '').strip() or None
        for number, page in enumerate(pdf.pages, start=1):
            found = page.find_tables()
            for t in found:
                table = _make_table(None, t.extract(), page=number)
                if table is not None:
                    tables.append(table)
            # Текст таблиц иначе попал бы в чанки дважды: и как текст, и как таблица.
            bboxes = [t.bbox for t in found]
            text_page = page.filter(_outside(bboxes)) if bboxes else page
            pages.append(text_page.extract_text() or '')
    if not any(p.strip() for p in pages) and not tables:
        logger.warning('%s: в PDF нет текстового слоя (скан?), OCR не поддерживается', source)
    return ParsedDocument(source=source, title=title, text='\n\n'.join(pages), tables=tables)


def _outside(bboxes: list[tuple[float, float, float, float]]) -> Callable[[dict[str, Any]], bool]:
    def keep(obj: dict[str, Any]) -> bool:
        if 'x0' not in obj or 'top' not in obj:
            return True
        cx = (obj['x0'] + obj['x1']) / 2
        cy = (obj['top'] + obj['bottom']) / 2
        return not any(x0 <= cx <= x1 and top <= cy <= bottom for x0, top, x1, bottom in bboxes)

    return keep


_PARSERS: dict[str, Callable[[bytes, str], ParsedDocument]] = {
    '.csv': _parse_csv,
    '.tsv': _parse_csv,
    '.xlsx': _parse_xlsx,
    '.xlsm': _parse_xlsx,
    '.docx': _parse_docx,
    '.pdf': _parse_pdf,
}
