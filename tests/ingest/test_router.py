from pathlib import Path

import pytest

from app.chunkers.base import ParsedDocument, Table, flatten
from app.config import Settings
from app.ingest.parsers import parse_bytes
from app.ingest.router import chunk_document, detect_doc_type, looks_like_legal

FIXTURES = Path(__file__).parent.parent / 'fixtures'


def _parse(name: str) -> ParsedDocument:
    return parse_bytes((FIXTURES / name).read_bytes(), name)


@pytest.mark.parametrize(
    ('name', 'expected'),
    [
        ('contract.txt', 'contract'),
        ('npa.txt', 'contract'),
        ('sample_module.py', 'code'),
        ('sample.ts', 'code'),
        ('report.csv', 'table'),
    ],
)
def test_detect_doc_type_on_fixtures(name: str, expected: str) -> None:
    assert detect_doc_type(_parse(name)) == expected


def test_markdown_is_docs() -> None:
    doc = parse_bytes(b'# API\n\n## Install\n\npip install x\n', 'README.md')

    assert detect_doc_type(doc) == 'docs'


def test_numbered_list_without_legal_terms_is_text() -> None:
    text = '\n'.join(f'1.{i} Нагрейте духовку и перемешайте тесто.' for i in range(1, 8))

    assert not looks_like_legal(text)
    assert detect_doc_type(ParsedDocument(source='recipe.txt', text=text)) == 'text'


def test_english_agreement_is_legal() -> None:
    text = 'This Agreement is made between the Parties.\n' + '\n'.join(
        f'Section {i}. Term\n{i}.1 The Licensee shall pay.' for i in range(1, 3)
    )

    assert looks_like_legal(text)


def test_pdf_report_dominated_by_tables_is_table() -> None:
    table = Table(None, ['Показатель', '2024'], [[f'Статья {i}', str(i * 1000)] for i in range(30)])
    doc = ParsedDocument(source='report.pdf', text='Отчёт о прибылях', tables=[table])

    assert detect_doc_type(doc) == 'table'
    assert detect_doc_type(ParsedDocument(source='memo.pdf', text='Служебная записка')) == 'text'


def test_naive_mode_uses_fixed_window_for_every_domain() -> None:
    settings = Settings(chunker_mode='naive', naive_window_tokens=64, chunk_overlap_tokens=8)

    chunks = chunk_document(_parse('contract.txt'), 'contract', settings)

    assert len(chunks) > 1
    assert {c.chunk_type for c in chunks} == {'text'}
    assert all(not c.children for c in chunks)


def test_contract_with_tables_gets_table_chunks() -> None:
    doc = _parse('contract.txt')
    spec = Table('Спецификация', ['Товар', 'Цена'], [['Цемент', '500']])
    with_table = ParsedDocument(source=doc.source, text=doc.text, tables=[spec])

    records = flatten(chunk_document(with_table, 'contract', Settings()))

    types = {r.chunk_type for r in records}
    assert 'clause' in types
    assert 'table' in types
    # Текст договора не продублирован табличным чанкером как обычный текст.
    assert sum('Поставщик обязуется передать' in r.content for r in records) == sum(
        'Поставщик обязуется передать' in r.content
        for r in flatten(chunk_document(doc, 'contract', Settings()))
    )


def test_code_and_docs_use_their_chunkers() -> None:
    code = chunk_document(_parse('sample_module.py'), 'code', Settings())
    docs = chunk_document(
        parse_bytes(b'# Guide\n\n## Setup\n\nRun it.\n', 'guide.md'), 'docs', Settings()
    )

    assert {c.ts_config for c in flatten(code)} == {'simple'}
    assert {c.chunk_type for c in docs} == {'doc_section'}
