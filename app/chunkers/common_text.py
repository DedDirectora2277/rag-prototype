"""Нарезка обычного текста: рекурсивная по структуре, naive-окно и Markdown/rst по заголовкам."""

import re
from dataclasses import dataclass
from pathlib import PurePath

from app.chunkers.base import Chunk, ParsedDocument, count_tokens, get_encoding

# Разделители от крупных к мелким. Шаблоны нулевой ширины: разделитель остаётся в тексте,
# поэтому склейка кусков восстанавливает исходный текст.
_SEPARATORS = (
    re.compile(r'(?<=\n\n)'),  # абзацы
    re.compile(r'(?<=\n)'),  # строки
    re.compile(r'(?<=[.!?…;])(?=\s)'),  # предложения
    re.compile(r'(?<=\s)(?=\S)'),  # слова
)

BREADCRUMB_SEP = ' → '


def _hard_split(text: str, max_tokens: int) -> list[str]:
    """Режет текст по символам на максимальные префиксы, влезающие в лимит."""
    pieces = []
    while text:
        lo, hi = 1, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if count_tokens(text[:mid]) <= max_tokens:
                lo = mid
            else:
                hi = mid - 1
        pieces.append(text[:lo])
        text = text[lo:]
    return pieces


def _split_pieces(text: str, max_tokens: int, level: int = 0) -> list[str]:
    """Дробит текст на куски не больше лимита, спускаясь по уровням разделителей."""
    if count_tokens(text) <= max_tokens:
        return [text]
    if level == len(_SEPARATORS):
        return _hard_split(text, max_tokens)
    pieces = []
    for part in _SEPARATORS[level].split(text):
        if part:
            pieces.extend(_split_pieces(part, max_tokens, level + 1))
    return pieces


def _overlap_tail(pieces: list[str], overlap_tokens: int) -> list[str]:
    """Хвост из последних кусков суммарно не больше `overlap_tokens`."""
    tail: list[str] = []
    for piece in reversed(pieces):
        if count_tokens(''.join([piece, *tail])) > overlap_tokens:
            break
        tail.insert(0, piece)
    return tail


def split_text(text: str, max_tokens: int, overlap_tokens: int = 0) -> list[str]:
    """Рекурсивно режет текст по абзацам, строкам, предложениям и словам.

    Мелкие соседние куски жадно склеиваются до лимита. Новый чанк начинается
    с хвоста предыдущего (перекрытие по границе предложения или слова).

    Args:
        text: Текст.
        max_tokens: Максимальный размер чанка в токенах.
        overlap_tokens: Размер перекрытия в токенах (0 — без перекрытия).

    Returns:
        Непустые чанки без пробелов по краям.
    """
    if not text.strip():
        return []
    if max_tokens <= 0:
        raise ValueError(f'max_tokens={max_tokens} должен быть положительным')

    chunks: list[str] = []
    current: list[str] = []
    for piece in _split_pieces(text, max_tokens):
        if not current or count_tokens(''.join([*current, piece])) <= max_tokens:
            current.append(piece)
            continue
        chunks.append(''.join(current))
        tail = _overlap_tail(current, overlap_tokens) if overlap_tokens > 0 else []
        while tail and count_tokens(''.join([*tail, piece])) > max_tokens:
            tail.pop(0)
        current = [*tail, piece]
    chunks.append(''.join(current))
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def naive_split(text: str, window_tokens: int, overlap_tokens: int = 0) -> list[str]:
    """Фиксированное окно по токенам без учёта структуры (baseline для ablation).

    Args:
        text: Текст.
        window_tokens: Размер окна в токенах.
        overlap_tokens: Перекрытие соседних окон в токенах.

    Returns:
        Непустые окна текста.
    """
    if not 0 <= overlap_tokens < window_tokens:
        raise ValueError(f'нужно 0 <= overlap_tokens < window_tokens, а не {overlap_tokens}')
    encoding = get_encoding()
    tokens = encoding.encode(text, disallowed_special=())
    step = window_tokens - overlap_tokens
    windows = []
    for start in range(0, len(tokens), step):
        window = b''.join(encoding.decode_tokens_bytes(tokens[start : start + window_tokens]))
        # Окно может разрезать многобайтный символ — обрезки отбрасываем.
        windows.append(window.decode('utf-8', errors='ignore').strip())
        if start + window_tokens >= len(tokens):
            break
    return [window for window in windows if window]


def doc_label(doc: ParsedDocument) -> str:
    """Короткое имя документа для breadcrumb: заголовок или имя файла."""
    return doc.title or PurePath(doc.source).name


@dataclass(frozen=True, slots=True)
class CommonTextChunker:
    """Рекурсивная нарезка повествовательного текста с перекрытием."""

    max_tokens: int = 512
    overlap_tokens: int = 64

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        """Нарезает `doc.text` на чанки типа `text`.

        Args:
            doc: Разобранный документ.

        Returns:
            Плоский список чанков.
        """
        return [
            Chunk(content=piece, chunk_type='text', metadata={'part': i})
            for i, piece in enumerate(split_text(doc.text, self.max_tokens, self.overlap_tokens))
        ]


@dataclass(frozen=True, slots=True)
class NaiveChunker:
    """Фиксированное окно по токенам — baseline `chunker_mode='naive'`."""

    window_tokens: int = 512
    overlap_tokens: int = 64

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        """Нарезает `doc.text` и таблицы (как текст) фиксированным окном.

        Args:
            doc: Разобранный документ.

        Returns:
            Плоский список чанков типа `text`.
        """
        text = '\n\n'.join(
            [doc.text]
            + ['\n'.join(' | '.join(row) for row in [t.header, *t.rows]) for t in doc.tables]
        )
        return [
            Chunk(content=piece, chunk_type='text', metadata={'part': i})
            for i, piece in enumerate(naive_split(text, self.window_tokens, self.overlap_tokens))
        ]


_MD_HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$')
_MD_FENCE = re.compile(r'^\s*(```|~~~)')
_RST_UNDERLINE = re.compile(r'^([=\-~^"\'`#*+])\1{2,}\s*$')


def _split_sections(text: str) -> list[tuple[list[str], str]]:
    """Делит Markdown/rst на секции `(путь заголовков, тело)`."""
    lines = text.splitlines()
    sections: list[tuple[list[str], str]] = []
    path: list[tuple[int, str]] = []
    body: list[str] = []
    rst_levels: list[str] = []  # в rst уровень задаётся порядком появления символа
    in_fence = False

    def flush() -> None:
        if ''.join(body).strip():
            sections.append(([title for _, title in path], '\n'.join(body)))
        body.clear()

    def open_heading(level: int, title: str) -> None:
        flush()
        while path and path[-1][0] >= level:
            path.pop()
        path.append((level, title))

    i = 0
    while i < len(lines):
        line = lines[i]
        if _MD_FENCE.match(line):
            in_fence = not in_fence
        elif not in_fence and (m := _MD_HEADING.match(line)):
            open_heading(len(m.group(1)), m.group(2))
            i += 1
            continue
        elif (
            not in_fence
            and line.strip()
            and i + 1 < len(lines)
            and (u := _RST_UNDERLINE.match(lines[i + 1]))
            and len(lines[i + 1].strip()) >= len(line.strip())
        ):
            char = u.group(1)
            if char not in rst_levels:
                rst_levels.append(char)
            open_heading(rst_levels.index(char) + 1, line.strip())
            i += 2
            continue
        body.append(line)
        i += 1
    flush()
    return sections


@dataclass(frozen=True, slots=True)
class MarkdownChunker:
    """Нарезка Markdown/rst по заголовкам с breadcrumb `Документ → H1 → H2`."""

    max_tokens: int = 512
    overlap_tokens: int = 64

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        """Нарезает документацию: секция по заголовкам, внутри — `split_text`.

        Args:
            doc: Разобранный документ.

        Returns:
            Плоский список чанков типа `doc_section`.
        """
        chunks = []
        for headings, body in _split_sections(doc.text):
            breadcrumb = BREADCRUMB_SEP.join([doc_label(doc), *headings])
            budget = max(self.max_tokens - count_tokens(breadcrumb) - 2, self.max_tokens // 2)
            for i, piece in enumerate(split_text(body, budget, self.overlap_tokens)):
                chunks.append(
                    Chunk(
                        content=f'{breadcrumb}\n\n{piece}',
                        chunk_type='doc_section',
                        metadata={'breadcrumb': breadcrumb, 'headings': headings, 'part': i},
                    )
                )
        return chunks
