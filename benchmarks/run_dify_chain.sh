#!/usr/bin/env bash
# Dify: дождаться загрузки корпуса → переиндексировать упавшие документы → прогон eval.
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS=benchmarks/results/logs
log() { echo "$(date '+%F %T') $*" | tee -a "$LOGS/night.log"; }
while pgrep -f 'benchmarks.run_dify ingest' >/dev/null; do sleep 60; done
log 'dify: индексация завершена, повтор упавших документов'
poetry run python -m benchmarks.run_dify retry >>"$LOGS/dify_retry.log" 2>&1 || { log 'dify: retry не удался'; exit 1; }
log 'dify: старт eval'
poetry run python -m benchmarks.run_dify eval >>"$LOGS/dify_eval.log" 2>&1
log "dify: eval завершён с кодом $?"
