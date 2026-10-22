import pytest

from benchmarks.dataset import Sample
from benchmarks.metrics import bootstrap_ci, score_sample


def _sample() -> Sample:
    return Sample(
        's',
        'tables',
        'q',
        'a',
        [],
        [['Общая выручка', '807186'], ['Чистая прибыль', '35217']],
        ['tables/ru/mts.xlsx', 'tables/ru/mts.pdf'],
    )


def test_score_sample_ranks_and_recall() -> None:
    contexts = [
        'шум',
        '| Общая выручка | 703741 | 807186 |',
        'Чистая прибыль: 35 217 млн',
        'ещё шум',
    ]
    sources = [
        'x',
        'benchmarks/corpus/tables/ru/mts.xlsx',
        'benchmarks/corpus/tables/ru/mts.xlsx',
        'y',
    ]
    scores = score_sample(_sample(), contexts, sources)
    assert scores['evidence_recall'] == 1.0
    assert scores['hit'] == 1.0
    assert scores['mrr'] == pytest.approx(1 / 2)
    assert scores['precision'] == pytest.approx(2 / 4)
    assert scores['ap'] == pytest.approx((1 / 2 + 2 / 3) / 2)
    assert scores['doc_recall'] == pytest.approx(1 / 2)


def test_score_sample_partial_group_is_not_relevant() -> None:
    scores = score_sample(_sample(), ['Общая выручка 703741'], ['x'])
    assert scores == {
        'evidence_recall': 0.0,
        'hit': 0.0,
        'mrr': 0.0,
        'precision': 0.0,
        'ap': 0.0,
        'doc_recall': 0.0,
    }


def test_bootstrap_ci_bounds_mean() -> None:
    mean, low, high = bootstrap_ci([0.0, 1.0] * 50)
    assert mean == 0.5
    assert low < 0.5 < high
