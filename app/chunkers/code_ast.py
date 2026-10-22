"""AST-нарезка исходного кода через tree-sitter.

Функции и методы становятся отдельными чанками с контекстным заголовком (путь, класс,
сигнатура, первая строка docstring). Большой класс — parent для своих методов, большая
функция — parent для частей, нарезанных по statement. Мелкие соседние узлы (импорты,
константы, короткие функции) склеиваются в один чанк.
"""

import itertools
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import tree_sitter_language_pack as tslp
from tree_sitter import Node, Parser

from app.chunkers.base import Chunk, ParsedDocument, count_tokens
from app.chunkers.common_text import CommonTextChunker, split_text

logger = logging.getLogger(__name__)

_COMMENT_TYPES = frozenset({'comment', 'line_comment', 'block_comment'})
_FUNCTION_VALUES = frozenset({'arrow_function', 'function_expression', 'function'})
_WRAPPER_FIELDS = ('definition', 'declaration')


@dataclass(frozen=True, slots=True)
class LanguageSpec:
    """Какие узлы грамматики считаются определениями.

    Attributes:
        definitions: Тип узла → вид (`function`, `class`, `type`). Узлы вида `class`
            — контейнеры: их члены нарезаются отдельно.
        wrappers: Обёртки (декораторы, `export`), внутри которых лежит определение.
    """

    definitions: dict[str, str]
    wrappers: frozenset[str] = field(default_factory=frozenset)


_JS_DEFINITIONS = {
    'function_declaration': 'function',
    'generator_function_declaration': 'function',
    'method_definition': 'function',
    'class_declaration': 'class',
    'abstract_class_declaration': 'class',
}
_TS_DEFINITIONS = {
    **_JS_DEFINITIONS,
    'interface_declaration': 'type',
    'type_alias_declaration': 'type',
    'enum_declaration': 'type',
}

LANGUAGES: dict[str, LanguageSpec] = {
    'python': LanguageSpec(
        definitions={'function_definition': 'function', 'class_definition': 'class'},
        wrappers=frozenset({'decorated_definition'}),
    ),
    'javascript': LanguageSpec(_JS_DEFINITIONS, frozenset({'export_statement'})),
    'typescript': LanguageSpec(_TS_DEFINITIONS, frozenset({'export_statement'})),
    'tsx': LanguageSpec(_TS_DEFINITIONS, frozenset({'export_statement'})),
    'go': LanguageSpec(
        {
            'function_declaration': 'function',
            'method_declaration': 'function',
            'type_declaration': 'type',
        }
    ),
    'java': LanguageSpec(
        {
            'method_declaration': 'function',
            'constructor_declaration': 'function',
            'class_declaration': 'class',
            'interface_declaration': 'class',
            'enum_declaration': 'class',
            'record_declaration': 'class',
        }
    ),
}


@lru_cache
def _get_parser(language: str) -> Parser:
    return tslp.get_parser(language)


def _text(node: Node) -> str:
    return (node.text or b'').decode('utf-8', errors='replace')


def _unwrap(node: Node, spec: LanguageSpec) -> Node:
    """Достаёт определение из обёрток (`@decorator`, `export`)."""
    while node.type in spec.wrappers:
        inner = next(
            (n for name in _WRAPPER_FIELDS if (n := node.child_by_field_name(name)) is not None),
            None,
        )
        if inner is None:
            break
        node = inner
    return node


def _arrow_declarator(node: Node) -> Node | None:
    """Для `const f = () => ...` возвращает declarator с функцией."""
    if node.type not in {'lexical_declaration', 'variable_declaration'}:
        return None
    for declarator in node.named_children:
        value = declarator.child_by_field_name('value')
        if value is not None and value.type in _FUNCTION_VALUES:
            return declarator
    return None


def _definition_kind(node: Node, spec: LanguageSpec) -> str | None:
    inner = _unwrap(node, spec)
    if inner.type in spec.definitions:
        return spec.definitions[inner.type]
    if _arrow_declarator(inner) is not None:
        return 'function'
    return None


def _name(inner: Node) -> str:
    target = _arrow_declarator(inner) or inner
    name = target.child_by_field_name('name')
    if name is None and inner.type == 'type_declaration':  # Go: type X struct{...}
        spec_node = next(iter(inner.named_children), None)
        name = spec_node.child_by_field_name('name') if spec_node is not None else None
    return _text(name) if name is not None else '<anonymous>'


def _signature(inner: Node) -> str:
    body = inner.child_by_field_name('body')
    raw = _text(inner)
    # Сигнатура — всё до тела; без тела (интерфейсы, объявления) — первая строка.
    raw = raw[: body.start_byte - inner.start_byte] if body is not None else raw.split('\n', 1)[0]
    return ' '.join(raw.split()).rstrip(':{ ').strip()


_QUOTES = re.compile(r'^[rbuRBU]*("""|\'\'\'|"|\')|("""|\'\'\'|"|\')$')
_COMMENT_MARKS = re.compile(r'^\s*(/\*\*?|\*/|\*|//+|#)\s?')


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        line = _COMMENT_MARKS.sub('', line).removesuffix('*/').strip()
        if line:
            return line
    return None


def _docstring_node(body: Node | None) -> Node | None:
    """Python-docstring: первый statement тела — строка (в старых грамматиках в обёртке)."""
    first = body.named_children[0] if body is not None and body.named_children else None
    if first is not None and first.type == 'expression_statement' and first.named_children:
        first = first.named_children[0]
    return first if first is not None and first.type == 'string' else None


def _docstring(inner: Node, lead: Sequence[Node]) -> str | None:
    if (string := _docstring_node(inner.child_by_field_name('body'))) is not None:
        return _first_line(_QUOTES.sub('', _text(string).strip()))
    if lead:
        return _first_line('\n'.join(_text(c) for c in lead))
    return None


def _set_ts_config(chunks: list[Chunk]) -> list[Chunk]:
    # Для кода — simple: идентификаторы не стеммятся.
    for chunk in chunks:
        chunk.ts_config = 'simple'
        _set_ts_config(chunk.children)
    return chunks


@dataclass(frozen=True, slots=True)
class _FileContext:
    path: str
    language: str
    spec: LanguageSpec
    lines: list[str]

    def slice(self, start_row: int, end_row: int) -> str:
        return '\n'.join(self.lines[start_row : end_row + 1])


@dataclass(frozen=True, slots=True)
class CodeAstChunker:
    """Чанкер исходного кода на tree-sitter.

    Attributes:
        max_tokens: Лимит размера чанка (с заголовком).
        min_tokens: Определения меньше этого склеиваются с соседями.
    """

    max_tokens: int = 512
    min_tokens: int = 40

    def chunk(self, doc: ParsedDocument) -> list[Chunk]:
        """Нарезает исходный файл по AST.

        Язык берётся из `doc.language` или определяется по расширению. Если язык
        не поддерживается или грамматика недоступна — обычная текстовая нарезка.

        Args:
            doc: Разобранный документ с исходным кодом в `doc.text`.

        Returns:
            Чанки верхнего уровня с `ts_config='simple'`.
        """
        language = doc.language or tslp.detect_language_from_path(doc.source)
        spec = LANGUAGES.get(language or '')
        parser = None
        if language and spec:
            try:
                parser = _get_parser(language)
            except tslp.Error as exc:
                logger.warning('грамматика %s недоступна: %s', language, exc)
        if parser is None or spec is None or language is None:
            return _set_ts_config(CommonTextChunker(self.max_tokens, 0).chunk(doc))

        tree = parser.parse(doc.text.encode('utf-8'))
        ctx = _FileContext(doc.source, language, spec, doc.text.splitlines())
        return _set_ts_config(self._chunk_nodes(ctx, tree.root_node.named_children, []))

    def _header(self, ctx: _FileContext, scope: list[str], signature: str | None) -> str:
        lines = [f'# path: {ctx.path}']
        if scope:
            lines.append(f'# class: {".".join(scope)}')
        if signature:
            lines.append(f'# {signature}')
        return '\n'.join(lines)

    def _chunk_nodes(
        self, ctx: _FileContext, nodes: Sequence[Node], scope: list[str]
    ) -> list[Chunk]:
        chunks: list[Chunk] = []
        glue: list[Node] = []
        comments: list[Node] = []
        for node in nodes:
            if node.type in _COMMENT_TYPES:
                comments.append(node)
                continue
            kind = _definition_kind(node, ctx.spec)
            if kind is None or (kind != 'class' and count_tokens(_text(node)) < self.min_tokens):
                glue.extend(comments)
                comments.clear()
                glue.append(node)
                continue
            # Комментарии вплотную над определением — его документация.
            lead: list[Node] = []
            while (
                comments
                and comments[-1].end_point.row + 1 >= (lead[0] if lead else node).start_point.row
            ):
                lead.insert(0, comments.pop())
            glue.extend(comments)
            comments.clear()
            chunks.extend(self._glue(ctx, glue, scope))
            glue.clear()
            chunks.extend(self._definition(ctx, node, lead, kind, scope))
        glue.extend(comments)
        chunks.extend(self._glue(ctx, glue, scope))
        return chunks

    def _glue(self, ctx: _FileContext, nodes: list[Node], scope: list[str]) -> list[Chunk]:
        """Склеивает мелкие соседние узлы в чанки до лимита."""
        header = self._header(ctx, scope, None)
        budget = self.max_tokens - count_tokens(header) - 1
        groups: list[list[Node]] = []
        for node in nodes:
            if groups:
                candidate = ctx.slice(groups[-1][0].start_point.row, node.end_point.row)
                if count_tokens(candidate) <= budget:
                    groups[-1].append(node)
                    continue
            groups.append([node])

        chunks = []
        for group in groups:
            start, end = group[0].start_point.row, group[-1].end_point.row
            text = ctx.slice(start, end)
            if not text.strip():
                continue
            symbols = [
                _name(_unwrap(n, ctx.spec))
                for n in group
                if _definition_kind(n, ctx.spec) is not None
            ]
            meta = self._meta(ctx, scope, 'module' if not scope else 'members', start, end)
            if symbols:
                meta['symbols'] = symbols
            for piece in split_text(text, budget) if count_tokens(text) > budget else [text]:
                chunks.append(
                    Chunk(content=f'{header}\n{piece}', chunk_type=meta['kind'], metadata={**meta})
                )
        return chunks

    def _meta(
        self, ctx: _FileContext, scope: list[str], kind: str, start_row: int, end_row: int
    ) -> dict[str, Any]:
        meta: dict[str, Any] = {
            'path': ctx.path,
            'language': ctx.language,
            'kind': kind,
            'start_line': start_row + 1,
            'end_line': end_row + 1,
        }
        if scope:
            meta['class'] = '.'.join(scope)
        return meta

    def _definition(
        self, ctx: _FileContext, node: Node, lead: list[Node], kind: str, scope: list[str]
    ) -> list[Chunk]:
        inner = _unwrap(node, ctx.spec)
        name = _name(inner)
        signature = _signature(inner)
        if doc := _docstring(inner, lead):
            signature = f'{signature}\n# doc: {doc}'
        start = (lead[0] if lead else node).start_point.row
        end = node.end_point.row
        text = ctx.slice(start, end)
        header = self._header(ctx, scope, signature)
        if kind == 'function' and scope:
            kind = 'method'
        meta = self._meta(ctx, scope, kind, start, end)
        meta['symbol'] = '.'.join([*scope, name])

        content = f'{header}\n{text}'
        if count_tokens(content) <= self.max_tokens:
            return [Chunk(content=content, chunk_type=kind, metadata=meta)]

        body = inner.child_by_field_name('body')
        children: list[Chunk] = []
        if kind == 'class' and body is not None:
            # Docstring класса уже есть в parent, отдельным чанком он только шумит.
            docstring = _docstring_node(body)
            members = [n for n in body.named_children if n != docstring]
            children = self._chunk_nodes(ctx, members, [*scope, name])
        if not children:
            children = self._split_statements(ctx, body, start, end, header, meta)
        return [Chunk(content=content, chunk_type=kind, metadata=meta, children=children)]

    def _split_statements(
        self,
        ctx: _FileContext,
        body: Node | None,
        start: int,
        end: int,
        header: str,
        meta: dict[str, Any],
    ) -> list[Chunk]:
        """Режет большое определение на части по границам statement в теле."""
        budget = self.max_tokens - count_tokens(header) - 8  # запас под «# part i/n»
        statements = body.named_children if body is not None else []
        if len(statements) == 1 and statements[0].type == 'statement_list':  # Go
            statements = statements[0].named_children

        cuts = [start]
        for stmt in statements:
            row = stmt.start_point.row
            if row > cuts[-1] and count_tokens(ctx.slice(cuts[-1], stmt.end_point.row)) > budget:
                cuts.append(row)
        bounds = [*cuts, end + 1]

        pieces: list[str] = []
        for seg_start, seg_end in itertools.pairwise(bounds):
            segment = ctx.slice(seg_start, seg_end - 1)
            pieces.extend(
                split_text(segment, budget) if count_tokens(segment) > budget else [segment]
            )
        return [
            Chunk(
                content=f'{header}\n# part {i + 1}/{len(pieces)}\n{piece}',
                chunk_type=f'{meta["kind"]}_part',
                metadata={**meta, 'part': i},
            )
            for i, piece in enumerate(pieces)
            if piece.strip()
        ]
