import pytest

from benchmarks.dataset import Sample, evidence_in, normalize, read_samples, write_samples
from benchmarks.prepare_datasets import validate


def test_normalize_whitespace_case_and_thousands() -> None:
    assert normalize('Итого  активов\n13 177 350,0') == 'итого активов 13177350,0'
    assert normalize('Net revenue $5,735') == normalize('net revenue $5735')
    assert normalize('Ёлка') == 'елка'


def test_normalize_keeps_non_thousands_commas() -> None:
    assert normalize('1,5 млрд, 2 кв.') == '1,5 млрд, 2 кв.'


@pytest.mark.parametrize(
    ('group', 'context', 'found'),
    [
        (['2014 net revenue', '$5,735'], '| 2014 net revenue | $5735 |', True),
        (['2014 net revenue', '$5,829'], '| 2014 net revenue | $5735 |', False),
        (['Арендатор  обязан'], 'арендатор обязан вносить плату', True),
    ],
)
def test_evidence_in(group: list[str], context: str, found: bool) -> None:
    assert evidence_in(group, normalize(context)) is found


def test_evidence_in_matches_prefix_of_long_fragment() -> None:
    fragment = 'a' * 300
    assert evidence_in([fragment], normalize('x ' + 'a' * 250))


def test_samples_roundtrip(tmp_path) -> None:
    sample = Sample('s-1', 'code', 'q?', 'a', ['ctx'], [['ctx']], ['code/x.py'], {'k': 1})
    path = tmp_path / 'd.jsonl'
    write_samples(path, [sample])
    assert read_samples(path) == [sample]


def test_validate_reports_missing_doc_and_fragment(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr('benchmarks.prepare_datasets.CORPUS_DIR', tmp_path)
    (tmp_path / 'doc.txt').write_text('Статья 1. Предмет договора', encoding='utf-8')
    good = Sample('ok', 'contracts', 'q', 'a', [], [['предмет  договора']], ['doc.txt'])
    bad = Sample('bad', 'contracts', 'q', 'a', [], [['цена']], ['doc.txt'])
    missing = Sample('missing', 'contracts', 'q', 'a', [], [['x']], ['nope.txt'])
    errors = validate([good, bad, missing, good])
    assert any(e.startswith('bad: фрагмент не найден') for e in errors)
    assert any(e.startswith('missing: нет документов') for e in errors)
    assert any(e.startswith('ok: повторяющийся id') for e in errors)
    assert not any(e.startswith('ok: фрагмент') for e in errors)
