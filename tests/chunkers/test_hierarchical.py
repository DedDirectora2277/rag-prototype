from pathlib import Path

from app.chunkers.base import Chunk, ParsedDocument, count_tokens, flatten
from app.chunkers.hierarchical import HierarchicalChunker, find_parties

FIXTURES = Path(__file__).parent.parent / 'fixtures'


def _doc(name: str) -> ParsedDocument:
    return ParsedDocument(source=f'fixtures/{name}', text=(FIXTURES / name).read_text('utf-8'))


def _sections(chunks: list[Chunk]) -> dict[str, Chunk]:
    return {c.metadata['section']: c for c in chunks if c.chunk_type == 'section'}


def test_contract_clause_is_child_of_section() -> None:
    sections = _sections(HierarchicalChunker().chunk(_doc('contract.txt')))

    section = sections['5']
    assert not section.is_retrievable
    assert [c.metadata['clause'] for c in section.children] == ['5.1', '5.2', '5.3']

    clause = section.children[1]
    assert clause.is_retrievable
    assert clause.chunk_type == 'clause'
    breadcrumb = 'ДОГОВОР ПОСТАВКИ № 17/2025 → 5. ОТВЕТСТВЕННОСТЬ СТОРОН → п. 5.2'
    assert clause.metadata['breadcrumb'] == breadcrumb
    assert clause.content.startswith(breadcrumb + '\n\n5.2. За нарушение срока оплаты')
    # Parent содержит весь раздел.
    assert '5.1. За нарушение срока поставки' in section.content
    assert '5.3. Уплата неустойки' in section.content


def test_subpoints_stick_to_their_clause() -> None:
    clause_2_2 = _sections(HierarchicalChunker().chunk(_doc('contract.txt')))['2'].children[1]

    assert clause_2_2.metadata['clause'] == '2.2'
    assert 'а) предоплата в размере 30%' in clause_2_2.content
    assert 'б) оставшиеся 70%' in clause_2_2.content
    assert '2.2.1. Датой оплаты' in clause_2_2.content


def test_section_intro_and_sections_without_clauses() -> None:
    sections = _sections(HierarchicalChunker().chunk(_doc('contract.txt')))

    # Текст раздела до первого пункта не теряется: он отдельный child без номера пункта.
    intro = sections['4'].children[0]
    assert 'clause' not in intro.metadata
    assert 'инструкциями П-6 и П-7' in intro.content
    # Раздел без пунктов сам ищется.
    assert sections['6'].is_retrievable
    assert 'действует до 31 декабря 2025 года' in sections['6'].content


def test_preamble_and_parties() -> None:
    chunks = HierarchicalChunker().chunk(_doc('contract.txt'))

    preamble = chunks[0]
    assert preamble.chunk_type == 'preamble'
    assert 'именуемое в дальнейшем «Поставщик»' in preamble.content
    assert all(c.metadata['parties'] == ['Поставщик', 'Покупатель'] for c in chunks)


def test_find_parties_english() -> None:
    text = (
        'ACME Corp. (hereinafter referred to as "Supplier") and Beta LLC '
        '(hereinafter "Customer") agree as follows.'
    )
    assert find_parties(text) == ['Supplier', 'Customer']


def test_npa_heading_hierarchy() -> None:
    chunks = HierarchicalChunker().chunk(_doc('npa.txt'))
    sections = _sections(chunks)

    # «Раздел III» и «Глава 23» без своего текста отдельными чанками не становятся.
    assert list(sections) == ['330', '331', '333']
    clause = sections['333'].children[0]
    assert clause.metadata['clause'] == '1'
    assert clause.metadata['breadcrumb'] == (
        'ГРАЖДАНСКИЙ КОДЕКС РОССИЙСКОЙ ФЕДЕРАЦИИ (выдержка)'
        ' → Раздел III. ОБЩАЯ ЧАСТЬ ОБЯЗАТЕЛЬСТВЕННОГО ПРАВА'
        ' → Глава 23. ОБЕСПЕЧЕНИЕ ИСПОЛНЕНИЯ ОБЯЗАТЕЛЬСТВ'
        ' → Статья 333. Уменьшение неустойки → п. 1'
    )
    assert sections['331'].is_retrievable


def test_long_clause_is_split_with_breadcrumb() -> None:
    long_clause = '1.1. ' + 'Поставщик обязуется соблюдать требования. ' * 200
    doc = ParsedDocument(source='c.txt', title='Договор', text=f'1. ОБЩИЕ\n{long_clause}')

    section = HierarchicalChunker(max_tokens=200, overlap_tokens=0).chunk(doc)[0]

    assert len(section.children) > 1
    for part, child in enumerate(section.children):
        assert child.content.startswith('Договор → 1. ОБЩИЕ → п. 1.1\n\n')
        assert child.metadata == {**child.metadata, 'clause': '1.1', 'part': part}
        assert count_tokens(child.content) <= 200


def test_unstructured_text_falls_back_to_common_text() -> None:
    doc = ParsedDocument(source='letter.txt', text='Просто письмо без пунктов.\n\nВторой абзац.')

    chunks = HierarchicalChunker().chunk(doc)

    assert [c.chunk_type for c in chunks] == ['text']


def test_flatten_contract_for_db() -> None:
    records = flatten(HierarchicalChunker().chunk(_doc('contract.txt')))

    for i, record in enumerate(records):
        if record.parent_index is not None:
            assert record.parent_index < i
            assert not records[record.parent_index].is_retrievable
    assert {r.ts_config for r in records} == {'russian'}
