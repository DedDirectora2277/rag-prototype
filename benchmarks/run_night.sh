#!/usr/bin/env bash
# Ночная цепочка прогонов (каждый шаг продолжается с места остановки при перезапуске):
#   1. дождаться ingest корпуса с доменными чанкерами в rag_bench;
#   2. baseline + ablation (vector/hybrid/hybrid_rerank/full) по rag_bench, ответы для full;
#   3. параллельно с п. 2 (он нагружает GPU, ingest — CPU): ingest корпуса naive-чанкингом
#      в rag_bench_naive, затем прогон naive без реранка, ответы для naive-vector.
# Логи: benchmarks/results/logs/*.log.
set -uo pipefail
cd "$(dirname "$0")/.."

PG='postgresql://rag:rag@localhost:5432'
LOGS=benchmarks/results/logs
mkdir -p "$LOGS"

log() { echo "$(date '+%F %T') $*" | tee -a "$LOGS/night.log"; }

wait_ingest() {
    while pgrep -f 'python -m app.ingest benchmarks/corpus$' >/dev/null; do sleep 60; done
}

domain_run() {
    log 'domain: старт прогона'
    RAG_DATABASE_DSN="$PG/rag_bench" poetry run python -m benchmarks.run_eval \
        --tag domain --generate full >>"$LOGS/run_domain.log" 2>&1
    log "domain: завершён с кодом $?"
}

naive_run() {
    docker exec rag-proto-postgres-1 psql -U rag -d rag -tAc \
        "select 1 from pg_database where datname='rag_bench_naive'" | grep -q 1 ||
        docker exec rag-proto-postgres-1 psql -U rag -d rag -c 'create database rag_bench_naive'
    docker exec rag-proto-postgres-1 psql -U rag -d rag_bench_naive -c \
        'create extension if not exists vector' >/dev/null
    log 'naive: старт ingest'
    RAG_DATABASE_DSN="$PG/rag_bench_naive" RAG_CHUNKER_MODE=naive \
        poetry run python -m app.ingest benchmarks/corpus >>"$LOGS/ingest_naive.log" 2>&1
    log "naive: ingest завершён с кодом $?"
    RAG_DATABASE_DSN="$PG/rag_bench_naive" poetry run python -m benchmarks.run_eval \
        --tag naive --configs vector hybrid --generate vector >>"$LOGS/run_naive.log" 2>&1
    log "naive: прогон завершён с кодом $?"
}

log 'ожидаю окончания ingest (domain)'
wait_ingest
log 'ingest (domain) завершён'
domain_run &
naive_run &
wait
log 'все прогоны завершены'
