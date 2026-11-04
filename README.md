# rag-proto

Прототип гетерогенной корпоративной RAG-системы и стенд для его
сравнения с Dify, FastGPT и AnythingLLM на трёх доменах: договоры и НПА, исходный код
и техническая документация, таблицы и финансовая отчётность.

Что отличает прототип от простого RAG:

- доменный чанкинг: Parent-Child для договоров и НПА (`app/chunkers/hierarchical.py`),
  AST на tree-sitter для кода (`code_ast.py`), строки таблиц с повторением шапки и таблица
  целиком как parent (`tables.py`), рекурсивная нарезка для остального текста (`common_text.py`);
- гибридный поиск в PostgreSQL: вектор (pgvector, HNSW) + полнотекст (`tsvector`), склейка RRF
  одним SQL-запросом (`app/db/queries.py`);
- переранжирование cross-encoder'ом и подстановка parent после реранка (`app/retrieval/hybrid.py`);
- генерация строго по контексту со ссылками [n] (`app/generation.py`).

## Стенд

Все модели вызываются через LiteLLM, общий для прототипа и конкурентов:

| Алиас | Модель | Где |
|---|---|---|
| `embed` | BAAI/bge-m3 | TEI, CPU |
| `rerank` | BAAI/bge-reranker-v2-m3 | TEI, GPU |
| `chat` | deepseek-v4-flash | OpenRouter |
| `judge` | qwen3.7-flash | OpenRouter |

```bash
cp .env.example .env                      # ключ OpenRouter
docker compose -f docker/docker-compose.yml up -d
poetry install --all-groups               # venv в .venv
```

Сервер: `poetry run uvicorn app.api.main:app` (`POST /ingest`, `POST /query`, `GET /health`).
Загрузка каталога из CLI: `poetry run python -m app.ingest <каталог>`.

## Воспроизведение результатов

1. Корпус и вопросы: `python -m benchmarks.prepare_datasets` скачивает 206 документов
   в `benchmarks/corpus/` и проверяет эталонные фрагменты 197 вопросов
   (`benchmarks/datasets/*.jsonl`, ручная проверка — `datasets/check_report.md`).
2. Прототип и простой RAG (корпус загружается в отдельные базы):
   ```bash
   RAG_DATABASE_DSN=.../rag_bench python -m app.ingest benchmarks/corpus
   RAG_DATABASE_DSN=.../rag_bench python -m benchmarks.run_eval --tag domain --generate full
   RAG_DATABASE_DSN=.../rag_bench_naive RAG_CHUNKER_MODE=naive python -m app.ingest benchmarks/corpus
   RAG_DATABASE_DSN=.../rag_bench_naive python -m benchmarks.run_eval --tag naive \
       --configs vector hybrid --generate vector
   ```
3. Конкуренты — по одному, см. `docker/competitors/README.md`:
   `python -m benchmarks.run_{dify,fastgpt,anythingllm} {setup,ingest,eval}`.
4. Оценка ответов LLM-судьёй: `python -m benchmarks.judge_answers <прогон>:<конфигурация> ...`;
   калибровка по ручной разметке — `python -m benchmarks.human_review`.
5. Отчёты и графики:
   ```bash
   python -m benchmarks.budget_recall   # полнота при равном бюджете контекста
   python -m benchmarks.paired_diff     # парные разности против Dify и FastGPT
   python -m benchmarks.sensitivity     # без вопросов с ошибочными эталонами
   python -m benchmarks.plots
   ```

Сырые результаты (`benchmarks/results/raw/`) в git не входят: контексты и ответы
перегенерируются шагами 2–4, всё остальное в `benchmarks/results/` строится из них.

## Результаты

| Файл | Что внутри |
|---|---|
| `benchmarks/results/<прогон>-retrieval.md` | метрики поиска без LLM: evidence recall, MRR, AP, … |
| `benchmarks/results/judge.md` | правильность и опора на контекст по оценке судьи |
| `benchmarks/results/judge_agreement.md` | согласие судьи с ручной разметкой |
| `benchmarks/results/equal_budget/` | полнота при равном бюджете контекста и парные разности |
| `benchmarks/results/sensitivity.md` | устойчивость выводов к ошибкам эталонов |
| `benchmarks/results/figures/` | графики |

## Данные и лицензии

Документы корпуса в репозиторий не входят: `benchmarks.prepare_datasets` скачивает их
из первоисточников в `benchmarks/corpus/` (каталог в `.gitignore`). В git лежат только
вопросы, эталонные ответы и короткие эталонные цитаты (`benchmarks/datasets/`) и манифест
корпуса с источником и лицензией каждого файла (`benchmarks/corpus_manifest.json`).
Атрибуция и тексты лицензий сторонних данных — `benchmarks/datasets/THIRD_PARTY_NOTICES.md`.

| Источник | Документов | Лицензия / статус |
|---|---|---|
| [CUAD](https://www.atticusprojectai.org/cuad) (The Atticus Project) | 30 | CC BY 4.0 |
| [FinQA](https://github.com/czyssrs/FinQA) (Chen et al., EMNLP 2021) | 80 | MIT, Copyright (c) 2021 Zhiyu Chen |
| [httpx](https://github.com/encode/httpx) 0.28.1, [click](https://github.com/pallets/click) 8.1.8 | 88 | BSD-3-Clause |
| ГК РФ (часть вторая), 44-ФЗ | 3 | официальные документы, не охраняются авторским правом (ст. 1259 ГК РФ) |
| Отчётность ПАО «Московская Биржа» и ПАО «МТС» | 4 | раскрытие информации эмитентом |
| Оферта Яндекс Облака | 1 | публичная оферта |

## Разработка

```bash
poetry run ruff check . && poetry run ruff format .
poetry run mypy
poetry run pytest    # интеграционные тесты пропускаются без Postgres из docker compose
```
