import io
from datetime import date

import docx
import pytest
from openpyxl import Workbook

from app.ingest.parsers import (
    UnsupportedFormatError,
    code_language,
    decode_text,
    is_supported,
    parse_bytes,
)


def _xlsx(sheets: dict[str, list[list[object]]]) -> bytes:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets.items():
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(row)
    buf = io.BytesIO()
    workbook.save(buf)
    return buf.getvalue()


def _pdf(lines: list[str]) -> bytes:
    """Минимальный PDF с одной страницей текста (Helvetica, только ASCII)."""
    content = (
        'BT /F1 12 Tf 72 720 Td 14 TL ' + ' '.join(f'({line}) Tj T*' for line in lines) + ' ET'
    )
    objects = [
        '<< /Type /Catalog /Pages 2 0 R >>',
        '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
        '/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
        f'<< /Length {len(content)} >>\nstream\n{content}\nendstream',
        '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    out = b'%PDF-1.4\n'
    offsets = []
    for n, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f'{n} 0 obj\n{obj}\nendobj\n'.encode()
    xref = len(out)
    out += f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode()
    out += ''.join(f'{o:010d} 00000 n \n' for o in offsets).encode()
    out += (
        f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()
    )
    return out


def test_decode_text_falls_back_to_cp1251() -> None:
    assert decode_text('Договор поставки\r\nп. 1.1'.encode('cp1251')) == 'Договор поставки\nп. 1.1'
    assert decode_text('﻿текст'.encode()) == 'текст'


def test_code_language_ignores_plain_text_and_markup() -> None:
    assert code_language('src/app.py') == 'python'
    assert code_language('main.go') == 'go'
    # tree-sitter считает .txt «vimdoc», а .csv — «csv»: это не код.
    assert code_language('notes.txt') is None
    assert code_language('README.md') is None
    assert code_language('report.csv') is None


def test_is_supported() -> None:
    assert all(is_supported(n) for n in ['a.pdf', 'a.docx', 'a.xlsx', 'a.csv', 'a.md', 'a.ts'])
    assert not is_supported('photo.jpg')
    assert not is_supported('archive.zip')


def test_parse_source_code_sets_language() -> None:
    doc = parse_bytes(b'def f():\n    return 1\n', 'pkg/mod.py', source='repo/pkg/mod.py')

    assert doc.language == 'python'
    assert doc.source == 'repo/pkg/mod.py'
    assert doc.metadata == {'filename': 'mod.py', 'extension': '.py'}


def test_parse_unsupported_raises() -> None:
    with pytest.raises(UnsupportedFormatError):
        parse_bytes(b'\x89PNG', 'image.png')


def test_parse_csv_sniffs_semicolon_and_cp1251() -> None:
    data = 'Показатель;2023;2024\nВыручка;1 250 300;1 480 750\n;;\n'.encode('cp1251')

    doc = parse_bytes(data, 'report.csv')

    [table] = doc.tables
    assert table.header == ['Показатель', '2023', '2024']
    assert table.rows == [['Выручка', '1 250 300', '1 480 750']]  # пустая строка выброшена


def test_parse_xlsx_sheets_cleans_empty_columns_and_formats_values() -> None:
    data = _xlsx(
        {
            'Баланс': [
                ['Статья', None, 'Сумма', 'Дата'],
                ['Касса', None, 1250300.0, date(2024, 12, 31)],
                [None, None, None, None],
                ['Банк', None, 12.5, None],
            ],
            'Пустой': [],
        }
    )

    doc = parse_bytes(data, 'balance.xlsx')

    [table] = doc.tables
    assert table.name == 'Баланс'
    assert table.metadata == {'sheet': 'Баланс'}
    assert table.header == ['Статья', 'Сумма', 'Дата']
    assert table.rows == [['Касса', '1250300', '2024-12-31'], ['Банк', '12.5', '']]


def test_parse_xlsx_default_sheet_name_is_dropped() -> None:
    doc = parse_bytes(_xlsx({'Sheet1': [['a', 'b'], [1, 2]]}), 'data.xlsx')

    assert doc.tables[0].name is None


def test_parse_docx_restores_auto_numbering_and_tables() -> None:
    document = docx.Document()
    document.core_properties.title = 'Договор поставки № 1'
    document.add_paragraph('ДОГОВОР ПОСТАВКИ')
    document.add_paragraph('Предмет договора', style='List Number')
    document.add_paragraph('Цена договора', style='List Number')
    table = document.add_table(rows=2, cols=2)
    for i, row in enumerate([['Товар', 'Цена'], ['Цемент', '500']]):
        for j, value in enumerate(row):
            table.cell(i, j).text = value
    buf = io.BytesIO()
    document.save(buf)

    doc = parse_bytes(buf.getvalue(), 'contract.docx')

    assert doc.title == 'Договор поставки № 1'
    assert doc.text.splitlines() == ['ДОГОВОР ПОСТАВКИ', '1. Предмет договора', '2. Цена договора']
    assert doc.tables[0].header == ['Товар', 'Цена']
    assert doc.tables[0].rows == [['Цемент', '500']]


def test_parse_pdf_extracts_text() -> None:
    doc = parse_bytes(_pdf(['SUPPLY AGREEMENT', '1.1 The Supplier shall deliver.']), 'a.pdf')

    assert 'SUPPLY AGREEMENT' in doc.text
    assert '1.1 The Supplier shall deliver.' in doc.text
    assert doc.tables == []
