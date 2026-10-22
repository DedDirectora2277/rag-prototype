import itertools
import re

import pytest

from app.chunkers.base import ParsedDocument, count_tokens
from app.chunkers.common_text import (
    CommonTextChunker,
    MarkdownChunker,
    NaiveChunker,
    naive_split,
    split_text,
)

PARAGRAPH = (
    'Поставщик обязуется передать товар в срок. Покупатель обязуется принять и оплатить товар! '
    'Стороны согласовали порядок приёмки; претензии направляются письменно. '
) * 6
TEXT = '\n\n'.join(f'Абзац {i}. {PARAGRAPH}' for i in range(5))


def _words(text: str) -> list[str]:
    return re.findall(r'\w+', text)


def test_split_text_respects_limit_and_covers_text() -> None:
    chunks = split_text(TEXT, max_tokens=80, overlap_tokens=0)

    assert len(chunks) > 5
    assert all(count_tokens(c) <= 80 for c in chunks)
    # Без перекрытия склейка чанков восстанавливает все слова текста по порядку.
    assert _words(' '.join(chunks)) == _words(TEXT)


def test_split_text_overlap() -> None:
    chunks = split_text(TEXT, max_tokens=80, overlap_tokens=20)

    assert all(count_tokens(c) <= 80 for c in chunks)
    for prev, nxt in itertools.pairwise(chunks):
        # Начало следующего чанка повторяет хвост предыдущего.
        head = ' '.join(_words(nxt)[:3])
        assert head in ' '.join(_words(prev))


def test_split_text_keeps_small_text_whole() -> None:
    assert split_text('  Короткий текст.  ', max_tokens=100) == ['Короткий текст.']
    assert split_text('   ', max_tokens=100) == []


def test_split_text_hard_splits_long_word() -> None:
    chunks = split_text('а' * 2000, max_tokens=50)

    assert all(count_tokens(c) <= 50 for c in chunks)
    assert ''.join(chunks) == 'а' * 2000


def test_naive_split_fixed_window() -> None:
    windows = naive_split(TEXT, window_tokens=100, overlap_tokens=10)

    assert len(windows) > 1
    # Окно режется по токенам исходного текста; при повторной токенизации обрезанный
    # на краю многобайтный символ может дать ±1 токен.
    assert all(count_tokens(w) <= 102 for w in windows)
    with pytest.raises(ValueError, match='overlap_tokens'):
        naive_split(TEXT, window_tokens=10, overlap_tokens=10)


def test_chunkers_produce_text_chunks() -> None:
    doc = ParsedDocument(source='doc.txt', text=TEXT)

    common = CommonTextChunker(max_tokens=80, overlap_tokens=10).chunk(doc)
    naive = NaiveChunker(window_tokens=80, overlap_tokens=10).chunk(doc)

    assert common and naive
    assert {c.chunk_type for c in common + naive} == {'text'}
    assert all(c.is_retrievable for c in common + naive)


def test_markdown_chunker_breadcrumbs() -> None:
    text = (
        '# Руководство\n'
        'Вступление.\n\n'
        '## Установка\n\n'
        '```bash\n'
        '# это комментарий, а не заголовок\n'
        'poetry install\n'
        '```\n\n'
        '## Запуск\n'
        'Команда uvicorn.\n'
    )
    chunks = MarkdownChunker().chunk(ParsedDocument(source='docs/README.md', text=text))

    crumbs = [c.metadata['breadcrumb'] for c in chunks]
    assert crumbs == [
        'README.md → Руководство',
        'README.md → Руководство → Установка',
        'README.md → Руководство → Запуск',
    ]
    install = chunks[1].content
    assert install.startswith('README.md → Руководство → Установка\n\n')
    assert '# это комментарий' in install


def test_markdown_chunker_rst_headings() -> None:
    text = 'API\n===\n\nОбзор.\n\nКлиент\n------\n\nМетоды клиента.\n'
    chunks = MarkdownChunker().chunk(ParsedDocument(source='api.rst', title='SDK', text=text))

    assert [c.metadata['headings'] for c in chunks] == [['API'], ['API', 'Клиент']]
    assert chunks[1].content.startswith('SDK → API → Клиент')
