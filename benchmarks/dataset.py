"""Формат вопросов бенчмарка и проверка эталонных фрагментов (evidence) без LLM."""

import json
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

Domain = Literal['contracts', 'code', 'tables']
DOMAINS: tuple[Domain, ...] = ('contracts', 'code', 'tables')

ROOT = Path(__file__).resolve().parent
CORPUS_DIR = ROOT / 'corpus'
DATASETS_DIR = ROOT / 'datasets'


@dataclass(frozen=True, slots=True)
class Sample:
    """Вопрос бенчмарка.

    Attributes:
        id: Уникальный id, префикс — источник (`cuad-`, `finqa-`, `ru-`, `code-`).
        domain: Домен.
        question: Вопрос пользователя.
        ground_truth: Эталонный ответ (reference для RAGAS).
        reference_contexts: Эталонные фрагменты в читаемом виде (для LLM-метрик RAGAS).
        evidence: Эталонные фрагменты для метрик без LLM. Каждый элемент — группа строк,
            которые все должны найтись в одном контексте; группа соответствует одному
            фрагменту (пункт договора, строка таблицы, функция).
        source_docs: Пути документов относительно `benchmarks/corpus/`.
        metadata: Происхождение вопроса (категория CUAD, программа FinQA и т.п.).
    """

    id: str
    domain: Domain
    question: str
    ground_truth: str
    reference_contexts: list[str]
    evidence: list[list[str]]
    source_docs: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


def read_samples(path: Path) -> list[Sample]:
    """Читает вопросы из jsonl.

    Args:
        path: Файл `*.jsonl`.

    Returns:
        Вопросы в порядке файла.
    """
    with path.open(encoding='utf-8') as f:
        return [Sample(**json.loads(line)) for line in f if line.strip()]


def write_samples(path: Path, samples: Iterable[Sample]) -> None:
    """Записывает вопросы в jsonl (одна строка — один вопрос).

    Args:
        path: Файл `*.jsonl`.
        samples: Вопросы.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for sample in samples:
            f.write(json.dumps(asdict(sample), ensure_ascii=False) + '\n')


_SPACES = re.compile(r'\s+')
# Разделители тысяч в числах: «5,735» и «5 735» сравниваются как «5735».
_THOUSANDS = re.compile(r'(?<=\d)[,  ](?=\d{3}\b)')


def normalize(text: str) -> str:
    """Нормализует текст для сравнения фрагментов между системами.

    Системы по-разному сериализуют текст (переносы строк, markdown/HTML таблиц,
    разделители тысяч), поэтому сравнение идёт по нормализованной форме.

    Args:
        text: Исходный текст.

    Returns:
        Текст в NFKC, в нижнем регистре, с одиночными пробелами и без разделителей тысяч.
    """
    text = unicodedata.normalize('NFKC', text).lower().replace('ё', 'е')
    text = _SPACES.sub(' ', text)
    return _THOUSANDS.sub('', text).strip()


# Длинные фрагменты (пункт договора целиком) системы режут на чанки по-разному;
# достаточно найти в контексте начало фрагмента.
EVIDENCE_PREFIX_CHARS = 200


def evidence_in(group: Sequence[str], context: str) -> bool:
    """Проверяет, содержит ли контекст эталонный фрагмент.

    Args:
        group: Строки одного фрагмента; должны найтись все.
        context: Текст контекста, который вернула система (уже нормализованный).

    Returns:
        `True`, если все строки группы (или их первые `EVIDENCE_PREFIX_CHARS` символов)
        входят в контекст.
    """
    return all(normalize(s)[:EVIDENCE_PREFIX_CHARS] in context for s in group)
