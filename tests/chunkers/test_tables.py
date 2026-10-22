import csv
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from app.chunkers.base import Chunk, ParsedDocument, Table, flatten
from app.chunkers.tables import TableChunker, normalize_number

FIXTURES = Path(__file__).parent.parent / 'fixtures'


def _csv_table(path: Path) -> Table:
    with path.open(encoding='utf-8', newline='') as f:
        header, *rows = list(csv.reader(f))
    return Table(name=None, header=header, rows=rows)


def _xlsx_tables(path: Path) -> list[Table]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    tables = []
    for sheet in workbook.worksheets:
        values = [
            ['' if v is None else str(v) for v in row] for row in sheet.iter_rows(values_only=True)
        ]
        tables.append(
            Table(
                name=sheet.title, header=values[0], rows=values[1:], metadata={'sheet': sheet.title}
            )
        )
    return tables


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        ('1 250 300', '1250300'),
        ('1 234,5', '1234.5'),
        ('1,234.5', '1234.5'),
        ('1,234', '1234'),
        ('12,5', '12.5'),
        ('(830 120)', '-830120'),
        ('−45', '-45'),
        ('22,1%', '22.1'),
        ('$1,200', '1200'),
        ('1.234.567', '1234567'),
        ('2024', '2024'),
        ('5.2.1', None),
        ('Выручка', None),
        ('-', None),
        ('', None),
    ],
)
def test_normalize_number(value: str, expected: str | None) -> None:
    assert normalize_number(value) == expected


def test_csv_report() -> None:
    doc = ParsedDocument(source='fixtures/report.csv', tables=[_csv_table(FIXTURES / 'report.csv')])

    [table] = TableChunker(rows_per_chunk=5).chunk(doc)

    assert table.chunk_type == 'table'
    assert not table.is_retrievable
    assert '| Чистая прибыль | 207 928 | 284 024 |' in table.content

    summary, *groups = table.children
    assert summary.chunk_type == 'table_summary'
    assert 'Единицы: тыс. руб.' in summary.content
    assert 'Период: 2023, 2024' in summary.content
    assert 'Строк: 14' in summary.content
    assert 'Чистая прибыль' in summary.content

    assert [(g.metadata['row_start'], g.metadata['row_end']) for g in groups] == [
        (1, 5),
        (6, 10),
        (11, 14),
    ]
    for group in groups:
        assert group.chunk_type == 'table_rows'
        assert '| Показатель (тыс. руб.) | 2023 | 2024 |' in group.content  # шапка повторяется
    # Нормализованные числа для FTS.
    assert '-830120' in groups[0].content
    assert '1250300' in groups[0].content
    assert {r.ts_config for r in flatten([table])} == {'russian'}


def test_row_groups_respect_token_limit() -> None:
    rows = [[f'Позиция {i}', 'очень длинное описание позиции ' * 5, str(i)] for i in range(30)]
    table = Table(name='Склад', header=['Позиция', 'Описание', 'Кол-во'], rows=rows)

    [parent] = TableChunker(rows_per_chunk=20, max_tokens=150).chunk(
        ParsedDocument(source='s.csv', tables=[table])
    )
    groups = parent.children[1:]

    assert len(groups) > 2
    assert sum(g.metadata['row_end'] - g.metadata['row_start'] + 1 for g in groups) == 30


def test_large_table_has_no_parent() -> None:
    rows = [[f'Строка {i}', str(i * 1000)] for i in range(200)]
    table = Table(name='Большая', header=['Название', 'Сумма'], rows=rows)

    chunks = TableChunker(parent_max_tokens=500).chunk(
        ParsedDocument(source='b.csv', tables=[table])
    )

    assert all(c.is_retrievable for c in chunks)
    assert chunks[0].chunk_type == 'table_summary'
    assert {c.chunk_type for c in chunks[1:]} == {'table_rows'}


def test_xlsx_sheets_and_surrounding_text(tmp_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = 'Balance 2024'
    sheet.append(['Item', 'USD in thousands', None])
    sheet.append(['Cash', 1200.5, None])
    sheet.append(['Receivables', 830, 'note 4'])
    path = tmp_path / 'report.xlsx'
    workbook.save(path)

    doc = ParsedDocument(
        source=str(path), text='Notes to the balance sheet.', tables=_xlsx_tables(path)
    )
    text, table = TableChunker().chunk(doc)

    assert text.chunk_type == 'text'
    summary: Chunk = table.children[0]
    assert 'Лист: Balance 2024' in summary.content
    assert 'Колонки: Item, USD in thousands, col3' in summary.content
    assert summary.metadata['units'] == 'in thousands'
    assert summary.metadata['period'] == ['2024']
    assert '| Cash | 1200.5 |  |' in table.children[1].content
    assert summary.ts_config == 'english'
