import subprocess
import sys
from pathlib import Path

import pytest
import tree_sitter_language_pack as tslp

from app.chunkers.base import Chunk, ParsedDocument, count_tokens, flatten
from app.chunkers.code_ast import CodeAstChunker

FIXTURES = Path(__file__).parent.parent / 'fixtures'


@pytest.fixture(scope='module', autouse=True)
def _grammars() -> None:
    # Грамматики tree-sitter скачиваются в ~/.cache при первом использовании.
    try:
        tslp.prefetch(['python', 'typescript'])
    except tslp.Error as exc:
        pytest.skip(f'грамматики tree-sitter недоступны: {exc}')


def _chunk(name: str, max_tokens: int = 512) -> list[Chunk]:
    doc = ParsedDocument(source=f'src/{name}', text=(FIXTURES / name).read_text('utf-8'))
    return CodeAstChunker(max_tokens=max_tokens).chunk(doc)


def _by_symbol(chunks: list[Chunk]) -> dict[str, Chunk]:
    found: dict[str, Chunk] = {}
    for chunk in chunks:
        if 'symbol' in chunk.metadata and chunk.metadata['symbol'] not in found:
            found[chunk.metadata['symbol']] = chunk
        found.update({k: v for k, v in _by_symbol(chunk.children).items() if k not in found})
    return found


def test_large_class_is_parent_of_methods() -> None:
    symbols = _by_symbol(_chunk('sample_module.py', max_tokens=200))

    warehouse = symbols['Warehouse']
    assert warehouse.chunk_type == 'class'
    assert not warehouse.is_retrievable
    assert [c.metadata['symbol'] for c in warehouse.children] == [
        'Warehouse.__init__',
        'Warehouse.put',
        'Warehouse.take',
        'Warehouse.total_value',
    ]
    # Docstring класса не становится отдельным чанком.
    assert all(c.chunk_type == 'method' for c in warehouse.children)


def test_method_has_context_header() -> None:
    take = _by_symbol(_chunk('sample_module.py', max_tokens=200))['Warehouse.take']

    assert take.content.startswith(
        '# path: src/sample_module.py\n'
        '# class: Warehouse\n'
        '# def take(self, sku: str, quantity: int) -> Item\n'
        '# doc: Списывает товар со склада и возвращает списанную позицию.\n'
        '    def take('
    )
    assert take.metadata['start_line'] == 38
    assert take.metadata['end_line'] == 46
    assert take.metadata['language'] == 'python'


def test_large_function_is_split_by_statements() -> None:
    func = _by_symbol(_chunk('sample_module.py', max_tokens=200))['calculate_penalty']

    assert not func.is_retrievable
    assert len(func.children) > 1
    assert all(c.chunk_type == 'function_part' for c in func.children)
    assert all(count_tokens(c.content) <= 200 for c in func.children)
    assert all('# def calculate_penalty(' in c.content for c in func.children)
    # Части покрывают всю функцию.
    assert 'return penalty' in func.children[-1].content


def test_small_nodes_are_glued() -> None:
    chunks = _chunk('sample_module.py')
    module = chunks[0]

    assert module.chunk_type == 'module'
    assert 'import math' in module.content
    assert 'MAX_ITEMS = 1000' in module.content
    assert module.metadata['symbols'] == ['add']


def test_small_class_stays_whole() -> None:
    symbols = _by_symbol(_chunk('sample_module.py'))

    assert symbols['Item'].is_retrievable
    assert '@dataclass' in symbols['Item'].content
    # С лимитом по умолчанию Warehouse помещается целиком.
    assert symbols['Warehouse'].is_retrievable


def test_all_code_chunks_use_simple_ts_config() -> None:
    records = flatten(_chunk('sample_module.py', max_tokens=200))

    assert {r.ts_config for r in records} == {'simple'}


def test_typescript() -> None:
    symbols = _by_symbol(_chunk('sample.ts'))

    assert set(symbols) >= {'parseCsvLine', 'ReportLoader', 'sumColumn'}
    parse = symbols['parseCsvLine']
    assert '# doc: Parses a CSV line into cells, honouring quoted values.' in parse.content
    assert '/**' in parse.content  # JSDoc вплотную над функцией входит в чанк
    assert symbols['sumColumn'].chunk_type == 'function'


def test_unknown_language_falls_back_to_text() -> None:
    doc = ParsedDocument(source='notes.unknownext', text='just some text\n\nmore text')

    chunks = CodeAstChunker().chunk(doc)

    assert [c.chunk_type for c in chunks] == ['text']
    assert chunks[0].ts_config == 'simple'


_TS_CHECK = """
import sys
from pathlib import Path
import tree_sitter_language_pack as tslp

src = Path(sys.argv[1]).read_bytes()
root = tslp.get_parser('python').parse(src).root_node
lines = src.count(b'\\n') + 1
for node in root.named_children:
    assert node.start_point.row <= lines, (node.start_point, node.start_byte)
    node.text
"""


def test_tree_sitter_keeps_node_points_valid() -> None:
    # tree-sitter 0.26.0 на этом файле отдаёт узлы с row == start_byte и падает с segfault
    # в node.text; проверка в подпроцессе, чтобы segfault не убил весь pytest.
    result = subprocess.run(
        [sys.executable, '-c', _TS_CHECK, str(FIXTURES / 'ts_node_corruption.py')],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-500:]


def test_chunks_file_that_crashed_tree_sitter_026() -> None:
    assert {'open_stream', '_wrap_io_open'} <= set(_by_symbol(_chunk('ts_node_corruption.py')))
