from benchmarks.adapters import corpus_files
from benchmarks.dataset import CORPUS_DIR
from benchmarks.run_dify import corpus_path as dify_corpus_path
from benchmarks.run_dify import dify_name
from benchmarks.run_fastgpt import _score, corpus_path, fastgpt_name


def test_name_roundtrip_for_corpus() -> None:
    for path in corpus_files():
        rel = str(path.relative_to(CORPUS_DIR))
        assert corpus_path(fastgpt_name(rel)) == rel
        assert dify_corpus_path(dify_name(rel)) == rel


def test_unsupported_suffix_uploaded_as_text() -> None:
    assert fastgpt_name('code/pkg/__init__.py') == 'code__pkg____init__.py.txt'
    assert fastgpt_name('contracts/a.docx') == 'contracts__a.docx'


def test_score_takes_first_value() -> None:
    item = {'score': [{'type': 'reRank', 'value': 0.9, 'index': 0}, {'type': 'rrf', 'value': 0.1}]}
    assert _score(item) == 0.9
    assert _score({}) == 0.0
