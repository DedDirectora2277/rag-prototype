"""Parent-Child нарезка договоров и нормативных актов по структуре разделов и пунктов.

Parent — раздел или статья целиком (в поиск не идёт), children — пункты с breadcrumb
вида «Договор → Раздел 5. Ответственность → п. 5.2». Если явных заголовков
(«Раздел», «Статья», «ARTICLE») нет, parent — пункт верхнего уровня «5.».
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.chunkers.base import Chunk, ParsedDocument, count_tokens
from app.chunkers.common_text import BREADCRUMB_SEP, CommonTextChunker, doc_label, split_text

# Ранг заголовка: чем меньше, тем выше уровень.
_HEADING_RANKS = {'раздел': 0, 'часть': 0, 'глава': 1, 'статья': 2, 'article': 0, 'section': 1}
_HEADING = re.compile(
    r'^\s*(?P<kind>Раздел|РАЗДЕЛ|Часть|ЧАСТЬ|Глава|ГЛАВА|Статья|СТАТЬЯ|Article|ARTICLE|Section|SECTION)'
    r'\s+(?P<num>[\dIVXLC]+)\.?(?:\s+(?P<title>\S.*))?$'
)
# Нумерованный пункт: «5.», «5.2», «5.2.1.» и т.п. Не больше трёх цифр, чтобы не ловить годы.
_ITEM = re.compile(r'^\s*(?P<num>\d{1,3}(?:\.\d{1,3})*)(?P<dot>\.?)\s+(?P<rest>\S.*)$')
_PARTIES = (
    re.compile(r'именуем\w*\s+в\s+дальнейшем\s+[«"“„]([^»"”“]{1,60})[»"”“]', re.IGNORECASE),
    re.compile(
        r'hereinafter\s+(?:referred\s+to\s+as\s+|called\s+)?(?:the\s+)?[(]?["“]([^"”]{1,60})["”]',
        re.IGNORECASE,
    ),
)
_MAX_TITLE_CHARS = 80


@dataclass(slots=True)
class _Clause:
    num: str | None
    lines: list[str]


@dataclass(slots=True)
class _Section:
    num: str
    heading: str  # строка заголовка, как в тексте
    path: list[str]  # заголовки предков + свой (для breadcrumb)
    intro: list[str] = field(default_factory=list)
    clauses: list[_Clause] = field(default_factory=list)
    base_depth: int | None = None  # глубина нумерации пунктов внутри секции


def _short(title: str) -> str:
    title = ' '.join(title.split())
    return title if len(title) <= _MAX_TITLE_CHARS else title[: _MAX_TITLE_CHARS - 1] + '…'


def find_parties(text: str) -> list[str]:
    """Извлекает обозначения сторон договора из преамбулы.

    Args:
        text: Текст договора.

    Returns:
        Обозначения сторон в порядке появления, без повторов.
    """
    parties: list[str] = []
    for pattern in _PARTIES:
        for m in pattern.finditer(text):
            name = m.group(1).strip()
            if name and name not in parties:
                parties.append(name)
    return parties


def _parse(lines: list[str]) -> tuple[list[str], list[_Section]]:
    """Разбирает строки на преамбулу и секции с пунктами."""
    has_headings = any(_HEADING.match(line) for line in lines)
    preamble: list[str] = []
    sections: list[_Section] = []
    stack: list[tuple[int, str]] = []  # (ранг, заголовок) для режима с заголовками

    for line in lines:
        heading = _HEADING.match(line) if has_headings else None
        item = None if heading else _ITEM.match(line)
        if heading:
            rank = _HEADING_RANKS[heading.group('kind').lower()]
            while stack and stack[-1][0] >= rank:
                stack.pop()
            stack.append((rank, _short(line)))
            sections.append(
                _Section(
                    num=heading.group('num'),
                    heading=line.strip(),
                    path=[title for _, title in stack],
                )
            )
            continue
        if item and not has_headings and '.' not in item.group('num') and item.group('dot'):
            # Режим без заголовков: «5. Ответственность сторон» открывает секцию.
            sections.append(
                _Section(num=item.group('num'), heading=line.strip(), path=[_short(line)])
            )
            continue
        if not sections:
            preamble.append(line)
            continue
        section = sections[-1]
        if item:
            depth = item.group('num').count('.') + 1
            if section.base_depth is None or depth <= section.base_depth:
                section.base_depth = depth
                section.clauses.append(_Clause(num=item.group('num'), lines=[line]))
                continue
        # Подпункты (а), 1), 5.2.1) и продолжения строк приклеиваются к текущему пункту.
        if section.clauses:
            section.clauses[-1].lines.append(line)
        else:
            section.intro.append(line)
    return preamble, sections


@dataclass(frozen=True, slots=True)
class HierarchicalChunker:
    """Parent-Child чанкер для договоров и НПА."""

    max_tokens: int = 512
    overlap_tokens: int = 64

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        """Нарезает договор: преамбула, секции (parent) и пункты (children).

        Args:
            doc: Разобранный документ.

        Returns:
            Чанки верхнего уровня; без распознанной структуры — как обычный текст.
        """
        preamble, sections = _parse(doc.text.splitlines())
        if not sections:
            return CommonTextChunker(self.max_tokens, self.overlap_tokens).chunk(doc)

        # Без заголовка документа первая строка преамбулы обычно и есть название договора.
        first_line = next((line for line in preamble if line.strip()), None)
        label = doc.title or (_short(first_line) if first_line else doc_label(doc))
        base_meta: dict[str, Any] = {}
        if parties := find_parties(doc.text):
            base_meta['parties'] = parties

        chunks = [
            Chunk(
                content=f'{label}\n\n{piece}',
                chunk_type='preamble',
                metadata={**base_meta, 'breadcrumb': label, 'part': i},
            )
            for i, piece in enumerate(self._split('\n'.join(preamble), label))
        ]
        for section in sections:
            # Заголовок без текста («Раздел II» перед статьями) уже есть в breadcrumb детей.
            if section.clauses or '\n'.join(section.intro).strip():
                chunks.append(self._section_chunk(section, label, base_meta))
        return chunks

    def _split(self, text: str, breadcrumb: str) -> list[str]:
        budget = max(self.max_tokens - count_tokens(breadcrumb) - 2, self.max_tokens // 2)
        return split_text(text, budget, self.overlap_tokens)

    def _leaf(
        self, text: str, breadcrumb: str, chunk_type: str, meta: dict[str, Any]
    ) -> list[Chunk]:
        pieces = self._split(text, breadcrumb)
        return [
            Chunk(
                content=f'{breadcrumb}\n\n{piece}',
                chunk_type=chunk_type,
                metadata={
                    **meta,
                    'breadcrumb': breadcrumb,
                    **({'part': i} if len(pieces) > 1 else {}),
                },
            )
            for i, piece in enumerate(pieces)
        ]

    def _section_chunk(self, section: _Section, label: str, base_meta: dict[str, Any]) -> Chunk:
        section_crumb = BREADCRUMB_SEP.join([label, *section.path])
        meta = {**base_meta, 'section': section.num}
        lines = [section.heading, *section.intro]
        for clause in section.clauses:
            lines.extend(clause.lines)
        full_text = '\n'.join(lines).strip()

        children: list[Chunk] = []
        if '\n'.join(section.intro).strip():
            children.extend(
                self._leaf(
                    '\n'.join([section.heading, *section.intro]), section_crumb, 'clause', meta
                )
            )
        for clause in section.clauses:
            crumb = BREADCRUMB_SEP.join([section_crumb, f'п. {clause.num}'])
            children.extend(
                self._leaf('\n'.join(clause.lines), crumb, 'clause', {**meta, 'clause': clause.num})
            )

        if not section.clauses:
            # Секция без пунктов: сама становится retrievable (или режется на части).
            leaves = self._leaf(full_text, section_crumb, 'section', meta)
            if len(leaves) == 1:
                return leaves[0]
            children = leaves
        return Chunk(
            content=f'{section_crumb}\n\n{full_text}',
            chunk_type='section',
            metadata={**meta, 'breadcrumb': section_crumb},
            children=children,
        )
