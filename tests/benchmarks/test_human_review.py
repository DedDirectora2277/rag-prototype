import math

import pytest

from benchmarks.human_review import cohen_kappa

ORDINAL = {'неверно': 0.0, 'частично': 0.5, 'верно': 1.0}


def test_kappa_perfect_agreement() -> None:
    pairs = [('да', 'да'), ('нет', 'нет'), ('да', 'да')]
    assert cohen_kappa(pairs) == pytest.approx(1.0)


def test_kappa_textbook_example() -> None:
    # 20 да/да, 5 да/нет, 10 нет/да, 15 нет/нет: p_o = 0.7, p_e = 0.5, κ = 0.4.
    pairs = [('да', 'да')] * 20 + [('да', 'нет')] * 5 + [('нет', 'да')] * 10
    pairs += [('нет', 'нет')] * 15
    assert cohen_kappa(pairs) == pytest.approx(0.4)


def test_weighted_kappa_penalizes_adjacent_less() -> None:
    adjacent = [('верно', 'верно'), ('неверно', 'неверно'), ('верно', 'частично')]
    distant = [('верно', 'верно'), ('неверно', 'неверно'), ('верно', 'неверно')]
    assert cohen_kappa(adjacent, ORDINAL) > cohen_kappa(distant, ORDINAL)


def test_kappa_undefined_when_single_label() -> None:
    assert math.isnan(cohen_kappa([('да', 'да'), ('да', 'да')]))
