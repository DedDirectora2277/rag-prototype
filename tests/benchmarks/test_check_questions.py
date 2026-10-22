import pytest

from benchmarks.check_questions import Result, number_supported, unsupported_numbers
from benchmarks.dataset import Sample


def _sample(answer: str, evidence: list[list[str]], **metadata: object) -> Sample:
    return Sample('s', 'tables', 'q', answer, [], evidence, ['d.xlsx'], dict(metadata))


@pytest.mark.parametrize(
    ('raw', 'value', 'evidence', 'found'),
    [
        ('807,2', 807.2, [807186.0], True),  # млн → млрд с округлением
        ('32,3', 32.3, [0.323], True),  # доля → проценты
        ('22739,9', 22739.9, [-22739.9], True),  # расходы со знаком минус
        ('24,9', 24.9, [62983.4, 78655.3], False),  # вычисленный прирост
    ],
)
def test_number_supported(raw: str, value: float, evidence: list[float], found: bool) -> None:
    assert number_supported(raw, value, evidence) is found


def test_unsupported_numbers_skips_references_laws_and_periods() -> None:
    sample = _sample(
        'За 6 месяцев на 31 декабря: 10 дней (ч. 13, 14 ст. 95 44-ФЗ, п. 12.5.1, 12.5.4).',
        [['через десять дней']],
    )
    assert unsupported_numbers(sample) == ['10']


def test_unsupported_numbers_checks_finqa_program_arguments() -> None:
    sample = _sample(
        '94',
        [['2014 net revenue', '$ 5735'], ['2015 net revenue', '$ 5829']],
        program='subtract(5829, 5735), divide(#0, const_100)',
    )
    assert unsupported_numbers(sample) == []


def test_result_flags_llm_disagreement() -> None:
    result = Result(_sample('1', [['1']]), [], [])
    result.llm = {
        'review': {'verdict': 'suspect', 'question_clear': False, 'answer_supported': True},
        'answer': 'x',
        'compare': {'match': 'partial'},
    }
    assert result.flags == [
        'LLM-вердикт: suspect',
        'вопрос неоднозначен',
        'решение моделью: partial',
    ]
