"""Собирает ручные вопросы в `manual/*.jsonl`: `python -m benchmarks.datasets.manual.build_manual`.

Вопросы написаны вручную по документам корпуса (полуавтоматическая разметка: черновик
вопросов и эталонных фрагментов подготовлен LLM-ассистентом по тексту документа,
затем вычитан автором). Эталонные фрагменты копируются из документа дословно,
`prepare_datasets` проверяет, что каждый из них есть в документе после парсинга.

Формат записи: (id, вопрос, эталонный ответ, документы, фрагменты). Фрагмент — строка
или кортеж строк, которые должны найтись в одном контексте (строка таблицы).
"""

from pathlib import Path

from benchmarks.dataset import Domain, Sample, write_samples
from benchmarks.datasets.manual import Entry
from benchmarks.datasets.manual.code_questions import CODE
from benchmarks.datasets.manual.contracts_ru import CONTRACTS_RU
from benchmarks.datasets.manual.tables_ru import TABLES_RU

MANUAL_DIR = Path(__file__).resolve().parent


def to_samples(entries: list[Entry], domain: Domain, language: str) -> list[Sample]:
    """Превращает записи в вопросы бенчмарка.

    Args:
        entries: Записи `(id, вопрос, ответ, документы, фрагменты)`.
        domain: Домен вопросов.
        language: Язык вопросов (`ru`, `en`).

    Returns:
        Вопросы с `metadata.source = 'manual'`.
    """
    samples = []
    for id_, question, answer, docs, evidence in entries:
        groups = [[e] if isinstance(e, str) else list(e) for e in evidence]
        samples.append(
            Sample(
                id=id_,
                domain=domain,
                question=question,
                ground_truth=answer,
                reference_contexts=[' | '.join(g) for g in groups],
                evidence=groups,
                source_docs=docs,
                metadata={'source': 'manual', 'language': language},
            )
        )
    return samples


def main() -> None:
    """Пишет `contracts_ru.jsonl`, `tables_ru.jsonl` и `code.jsonl`."""
    write_samples(MANUAL_DIR / 'contracts_ru.jsonl', to_samples(CONTRACTS_RU, 'contracts', 'ru'))
    write_samples(MANUAL_DIR / 'tables_ru.jsonl', to_samples(TABLES_RU, 'tables', 'ru'))
    write_samples(MANUAL_DIR / 'code.jsonl', to_samples(CODE, 'code', 'en'))


if __name__ == '__main__':
    main()
