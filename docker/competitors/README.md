# Стенды конкурентов

Конфигурации, на которых получены результаты Dify, FastGPT и AnythingLLM в `benchmarks/results/`.
Все системы ходят в LLM, эмбеддер и реранкер через LiteLLM стенда (`docker/docker-compose.yml`,
`host.docker.internal:4000`), поэтому перед запуском конкурента должен быть поднят основной стенд.
Запускать по одному: вместе с TEI они не помещаются в память ноутбука.

| Система | Версия | Порт | Запуск | Прогон |
|---|---|---|---|---|
| Dify | 1.17.1 | 8090 | см. ниже | `python -m benchmarks.run_dify {setup,ingest,retry,eval}` |
| FastGPT | 4.17.2 | 3000 | `docker compose -f fastgpt/docker-compose.yml up -d` | `python -m benchmarks.run_fastgpt {setup,ingest,eval}` |
| AnythingLLM | 1.18.0 | 3001 | `docker compose -f anythingllm/docker-compose.yml up -d` | `python -m benchmarks.run_anythingllm {setup,ingest,eval}` |

Dify слишком большой, чтобы копировать его compose: берётся официальный репозиторий
(`git clone --depth 1 --branch 1.17.1 https://github.com/langgenius/dify`), в `docker/.env`
копируется `.env.example`, поверх — значения из `dify/env.override` и свой `SECRET_KEY`,
затем `docker compose up -d` в `docker/`.
Индексация Dify нестабильна (исчерпание пула соединений к БД), поэтому после `ingest`
нужен шаг `retry`; в итоговом прогоне проиндексированы все 206 документов.

Отступления от настроек по умолчанию:

- FastGPT: убраны агентские песочницы, лимиты памяти (app 3 ГБ); минио — образ Chainguard
  (официальный удалён с Docker Hub); `aiproxy` оставлен, т.к. без него 4.17 не стартует.
  Реранк не используется: FastGPT шлёт ~120 кандидатов одним запросом с жёстким таймаутом 30 с
  и при таймауте молча возвращает выдачу без реранка.
- AnythingLLM: `EMBEDDING_MODEL_MAX_CHUNK_LENGTH` не задавать — он становится размером чанка
  (вместо 1000 символов по умолчанию).
