"""Метрики retrieval без LLM по эталонным фрагментам (`Sample.evidence`).

Контекст считается релевантным, если содержит хотя бы один эталонный фрагмент целиком
(все строки группы, см. `benchmarks.dataset.evidence_in`). Так метрики одинаково
считаются для любой системы, независимо от того, как она режет и сериализует документы.
"""

import random
import statistics
from collections.abc import Sequence

from benchmarks.dataset import Sample, evidence_in, normalize


def relevance(sample: Sample, contexts: Sequence[str]) -> list[set[int]]:
    """Для каждого контекста — индексы эталонных фрагментов, которые в нём есть.

    Args:
        sample: Вопрос с эталонными фрагментами.
        contexts: Тексты контекстов в порядке выдачи.

    Returns:
        Список множеств той же длины, что `contexts`.
    """
    normalized = [normalize(c) for c in contexts]
    return [{i for i, g in enumerate(sample.evidence) if evidence_in(g, c)} for c in normalized]


def score_sample(
    sample: Sample, contexts: Sequence[str], sources: Sequence[str]
) -> dict[str, float]:
    """Метрики одного вопроса.

    - `evidence_recall` — доля эталонных фрагментов, найденных в контекстах;
    - `hit` — найден ли хотя бы один фрагмент;
    - `mrr` — 1 / ранг первого релевантного контекста;
    - `precision` — доля релевантных контекстов среди выданных;
    - `ap` — average precision по релевантным позициям (аналог Context Precision RAGAS);
    - `doc_recall` — доля эталонных документов среди источников контекстов.

    Args:
        sample: Вопрос.
        contexts: Тексты контекстов.
        sources: Источники контекстов (пути файлов).

    Returns:
        Значения метрик.
    """
    rel = relevance(sample, contexts)
    found = set().union(*rel) if rel else set()
    relevant = [bool(r) for r in rel]
    first = next((i for i, r in enumerate(relevant) if r), None)
    hits = 0
    precisions = []
    for i, r in enumerate(relevant, start=1):
        if r:
            hits += 1
            precisions.append(hits / i)
    docs = {d for d in sample.source_docs if any(s.endswith(d) for s in sources)}
    return {
        'evidence_recall': len(found) / len(sample.evidence) if sample.evidence else 0.0,
        'hit': float(bool(found)),
        'mrr': 1 / (first + 1) if first is not None else 0.0,
        'precision': sum(relevant) / len(relevant) if relevant else 0.0,
        'ap': statistics.fmean(precisions) if precisions else 0.0,
        'doc_recall': len(docs) / len(sample.source_docs),
    }


def bootstrap_ci(
    values: Sequence[float], iterations: int = 2000, seed: int = 0
) -> tuple[float, float, float]:
    """Среднее и 95% bootstrap-интервал.

    Args:
        values: Значения метрики по вопросам.
        iterations: Число bootstrap-выборок.
        seed: Seed для воспроизводимости.

    Returns:
        `(mean, low, high)`.
    """
    if not values:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    means = sorted(statistics.fmean(rng.choices(values, k=n)) for _ in range(iterations))
    return statistics.fmean(values), means[int(0.025 * iterations)], means[int(0.975 * iterations)]
