"""Адаптеры систем-конкурентов и общие функции загрузки корпуса в них."""

import functools
from pathlib import Path

from benchmarks.dataset import CORPUS_DIR


def corpus_files() -> list[Path]:
    """Файлы корпуса для загрузки (без скрытых и lock-файлов Office `~$…`)."""
    return sorted(
        p for p in CORPUS_DIR.rglob('*') if p.is_file() and not p.name.startswith(('.', '~$'))
    )


def upload_name(rel: str, supported: frozenset[str]) -> str:
    """Имя файла в системе для пути корпуса: `/` → `__`, неподдерживаемым — суффикс `.txt`.

    Исходники и rst загружаются как текст: содержимое то же, меняется только расширение.
    """
    name = rel.replace('/', '__')
    return name if Path(name).suffix.lower() in supported else f'{name}.txt'


@functools.cache
def upload_names(supported: frozenset[str]) -> dict[str, str]:
    """Обратное отображение `upload_name`: имя в системе → путь в корпусе.

    Обратная замена `__` → `/` неоднозначна для имён вроде `__init__.py`, поэтому путь
    ищется среди файлов корпуса.
    """
    return {
        upload_name(str(p.relative_to(CORPUS_DIR)), supported): str(p.relative_to(CORPUS_DIR))
        for p in corpus_files()
    }
