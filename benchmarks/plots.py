"""Графики для презентации: `python -m benchmarks.plots` → `benchmarks/results/figures/*.png`.

Читает `results/<run>-summary.csv` (domain, naive, dify — какие есть). Цвет кодирует систему
(наша / простой RAG / Dify), а не ранг; палитра — первые три слота эталонной палитры
навыка dataviz (проверены на различимость при цветовой слепоте для всех пар).
Усы — 95% bootstrap CI.
"""

import csv
from collections.abc import Sequence
from pathlib import Path

import matplotlib as mpl

mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from benchmarks.run_eval import RESULTS_DIR

SURFACE = '#fcfcfb'
TEXT = '#0b0b0b'
TEXT_SECONDARY = '#52514e'
GRID = '#e4e3df'
COLORS = {'ours': '#2a78d6', 'naive': '#eb6834', 'dify': '#1baf7a'}

# (прогон, конфигурация) → (подпись, система). Порядок — порядок на графике.
CONFIGS: list[tuple[str, str, str, str]] = [
    ('naive', 'vector', 'Простой RAG: окно 512 + вектор', 'naive'),
    ('naive', 'hybrid', 'Окно 512 + вектор + FTS', 'naive'),
    ('dify', 'dify_vector', 'Dify: вектор', 'dify'),
    ('dify', 'dify_hybrid_rerank', 'Dify: гибрид + реранк', 'dify'),
    ('domain', 'vector', 'Наши чанкеры + вектор', 'ours'),
    ('domain', 'hybrid', '+ FTS (RRF)', 'ours'),
    ('domain', 'hybrid_rerank', '+ cross-encoder реранк', 'ours'),
    ('domain', 'full', '+ parent-expansion (полная система)', 'ours'),
]
DOMAIN_TITLES = {
    'all': 'Все домены',
    'contracts': 'Договоры и НПА',
    'code': 'Код и документация',
    'tables': 'Таблицы и отчёты',
}
METRIC_TITLES = {
    'evidence_recall': 'Доля найденных эталонных фрагментов в top-8 (evidence recall)',
    'mrr': 'MRR: 1 / ранг первого релевантного контекста',
    'ap': 'Average precision (аналог Context Precision)',
    'faithfulness': 'Faithfulness: доля утверждений ответа, подтверждённых контекстами',
    'correctness': 'Правильность ответа относительно эталона (LLM-судья)',
}
# Метрики ответов есть только у конфигураций, для которых генерировались ответы.
ANSWER_METRICS = ('faithfulness', 'correctness')
KEY_CONFIGS = {
    ('naive', 'vector'),
    ('dify', 'dify_vector'),
    ('dify', 'dify_hybrid_rerank'),
    ('domain', 'full'),
}
LEGEND = {
    'ours': 'Наша система (ablation)',
    'naive': 'Простой RAG (базовая линия)',
    'dify': 'Dify 1.17',
}

Row = tuple[float, float, float, int]


def load_summary(results_dir: Path = RESULTS_DIR) -> dict[tuple[str, str, str, str], Row]:
    """Читает все `*-summary.csv`: (прогон, конфигурация, домен, метрика) → (mean, low, high, n)."""
    data: dict[tuple[str, str, str, str], Row] = {}
    for path in sorted(results_dir.glob('*-summary.csv')):
        with path.open(encoding='utf-8') as f:
            for r in csv.DictReader(f):
                key = (r['run'], r['config'], r['domain'], r['metric'])
                data[key] = (float(r['mean']), float(r['ci_low']), float(r['ci_high']), int(r['n']))
    return data


def _style(ax: Axes) -> None:
    ax.set_facecolor(SURFACE)
    for side in ('top', 'right', 'left'):
        ax.spines[side].set_visible(False)
    ax.spines['bottom'].set_color(GRID)
    ax.tick_params(colors=TEXT_SECONDARY, length=0)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def bars(
    ax: Axes,
    data: dict[tuple[str, str, str, str], Row],
    domain: str,
    metric: str,
    configs: Sequence[tuple[str, str, str, str]],
    labels: bool = True,
) -> None:
    """Горизонтальные столбцы метрики по конфигурациям с усами CI и подписями значений.

    Позиции строк фиксированы списком `configs`: отсутствующая конфигурация оставляет пустую
    строку, чтобы строки совпадали между панелями.
    """
    runs = {k[0] for k in data}
    present = [c for c in configs if c[0] in runs]
    y = list(range(len(present)))[::-1]
    for yi, (run, config, _label, system) in zip(y, present, strict=True):
        if (run, config, domain, metric) not in data:
            ax.text(0.01, yi, 'нет данных', va='center', fontsize=8, color=TEXT_SECONDARY)
            continue
        mean, low, high, _ = data[(run, config, domain, metric)]
        ax.barh(yi, mean, height=0.62, color=COLORS[system], edgecolor=SURFACE, linewidth=2)
        ax.plot([low, high], [yi, yi], color=TEXT_SECONDARY, linewidth=1.2, solid_capstyle='butt')
        ax.text(
            high + 0.015, yi, f'{mean:.2f}', va='center', fontsize=9, color=TEXT, fontweight='bold'
        )
    ax.set_ylim(-0.6, len(present) - 0.4)
    ax.set_yticks(y)
    ax.set_yticklabels([c[2] for c in present] if labels else [''] * len(present), color=TEXT)
    ax.set_xlim(0, 1.12)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    _style(ax)


def _legend(fig: Figure, systems: Sequence[str]) -> None:
    handles = [Rectangle((0, 0), 1, 1, color=COLORS[s]) for s in systems]
    fig.legend(
        handles,
        [LEGEND[s] for s in systems],
        loc='lower center',
        ncol=len(systems),
        frameon=False,
        fontsize=9,
        labelcolor=TEXT_SECONDARY,
    )


def _systems(data: dict[tuple[str, str, str, str], Row]) -> list[str]:
    runs = {k[0] for k in data}
    return [
        s for s, run in (('ours', 'domain'), ('naive', 'naive'), ('dify', 'dify')) if run in runs
    ]


def figure_ablation(
    data: dict[tuple[str, str, str, str], Row],
    metric: str,
    path: Path,
    configs: Sequence[tuple[str, str, str, str]] = CONFIGS,
) -> None:
    """Один график: конфигурации на всех доменах."""
    height = 1.8 + 0.55 * len(configs)
    fig, ax = plt.subplots(figsize=(10, height), facecolor=SURFACE)
    bars(ax, data, 'all', metric, configs)
    counts = sorted({v[3] for k, v in data.items() if k[2] == 'all' and k[3] == metric})
    n = '/'.join(map(str, counts))
    fig.text(
        0.02, 1 - 0.15 / height, METRIC_TITLES[metric], ha='left', va='top', fontsize=13, color=TEXT
    )
    fig.text(
        0.02,
        1 - 0.5 / height,
        (
            f'n = {n} ответов без отказа «нет данных»; усы — 95% bootstrap CI'
            if metric == 'faithfulness'
            else f'n = {n} вопросов (договоры, код, таблицы; RU и EN); усы — 95% bootstrap CI'
        ),
        ha='left',
        va='top',
        fontsize=9,
        color=TEXT_SECONDARY,
    )
    _legend(fig, _systems(data))
    fig.tight_layout(rect=(0, 0.45 / height, 1, 1 - 0.8 / height))
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def figure_domains(data: dict[tuple[str, str, str, str], Row], metric: str, path: Path) -> None:
    """Малые кратные: ключевые конфигурации по доменам на общей шкале."""
    key = [
        c
        for c in CONFIGS
        if (c[0], c[1]) in {('naive', 'vector'), ('dify', 'dify_hybrid_rerank'), ('domain', 'full')}
    ]
    domains = ['contracts', 'code', 'tables']
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), facecolor=SURFACE, sharex=True)
    for i, (ax, domain) in enumerate(zip(axes, domains, strict=True)):
        bars(ax, data, domain, metric, key, labels=i == 0)
        ax.set_title(DOMAIN_TITLES[domain], loc='left', fontsize=11, color=TEXT)
    fig.text(0.01, 0.97, METRIC_TITLES[metric], ha='left', va='top', fontsize=13, color=TEXT)
    _legend(fig, _systems(data))
    fig.tight_layout(rect=(0, 0.08, 1, 0.9))
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)


def main(results_dir: Path = RESULTS_DIR) -> None:
    """Строит все графики по сводкам из `results_dir` в `results_dir/figures`."""
    figures = results_dir / 'figures'
    figures.mkdir(parents=True, exist_ok=True)
    data = load_summary(results_dir)
    for metric in ('evidence_recall', 'mrr', 'ap'):
        figure_ablation(data, metric, figures / f'ablation_{metric}.png')
        figure_domains(data, metric, figures / f'domains_{metric}.png')
    key = [c for c in CONFIGS if (c[0], c[1]) in KEY_CONFIGS]
    for metric in ANSWER_METRICS:
        figure_ablation(data, metric, figures / f'answers_{metric}.png', key)
        figure_domains(data, metric, figures / f'domains_{metric}.png')
    print(f'графики → {figures}')


if __name__ == '__main__':
    main()


def figure_budget(csv_path: Path, path: Path, domain: str = 'all') -> None:
    """Evidence recall в зависимости от бюджета контекста (из `budget_recall.csv`)."""
    series = [
        ('Простой RAG', COLORS['naive'], '-'),
        ('Dify top-24: гибрид + реранк', COLORS['dify'], '-'),
        ('Наша: чанкеры + гибрид + реранк', COLORS['ours'], '--'),
        ('Наша: полная (parent-expansion)', COLORS['ours'], '-'),
    ]
    rows: dict[str, list[tuple[int, float, float, float]]] = {}
    with csv_path.open(encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['domain'] == domain:
                rows.setdefault(r['system'], []).append(
                    (
                        int(r['budget_tokens']),
                        float(r['mean']),
                        float(r['ci_low']),
                        float(r['ci_high']),
                    )
                )
    fig, ax = plt.subplots(figsize=(10, 5.4), facecolor=SURFACE)
    ends: list[tuple[float, str]] = []
    for label, color, style in series:
        points = sorted(rows.get(label, []))
        if not points:
            continue
        xs = [p[0] for p in points]
        ax.fill_between(
            xs, [p[2] for p in points], [p[3] for p in points], color=color, alpha=0.08, linewidth=0
        )
        ax.plot(
            xs,
            [p[1] for p in points],
            style,
            color=color,
            linewidth=2,
            marker='o',
            markersize=6,
            label=label,
        )
        ends.append((points[-1][1], label))
    # Подписи у концов линий разносятся по вертикали, чтобы не накладывались.
    placed: list[float] = []
    for y, label in sorted(ends, reverse=True):
        y_text = min(y, placed[-1] - 0.035) if placed else y
        placed.append(y_text)
        ax.text(8000 * 1.06, y_text, label, va='center', fontsize=8.5, color=TEXT_SECONDARY)
    ax.set_xscale('log', base=2)
    ax.set_xticks([500, 1000, 2000, 4000, 8000])
    ax.set_xticklabels(['500', '1000', '2000', '4000', '8000'])
    ax.set_xlim(420, 8000 * 3.2)
    ax.set_ylim(0.3, 1.0)
    ax.set_xlabel('Бюджет контекста, токенов (в порядке ранжирования)', color=TEXT_SECONDARY)
    _style(ax)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.xaxis.grid(False)
    fig.text(
        0.02,
        0.97,
        'Evidence recall при равном бюджете контекста',
        ha='left',
        va='top',
        fontsize=13,
        color=TEXT,
    )
    fig.text(
        0.02,
        0.915,
        'Общее с Dify подмножество (142 вопроса); заливка — 95% bootstrap CI',
        ha='left',
        va='top',
        fontsize=9,
        color=TEXT_SECONDARY,
    )
    ax.legend(loc='lower center', frameon=False, fontsize=9, labelcolor=TEXT_SECONDARY, ncol=2)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)
