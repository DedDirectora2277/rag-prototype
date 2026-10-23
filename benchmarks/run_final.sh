#!/usr/bin/env bash
# Финал: дождаться eval Dify → судья для конфигураций Dify → сравнение на общем подмножестве.
set -uo pipefail
cd "$(dirname "$0")/.."
LOGS=benchmarks/results/logs
log() { echo "$(date '+%F %T') $*" | tee -a "$LOGS/night.log"; }
while pgrep -f 'python -m benchmarks.run_dify eval' >/dev/null; do sleep 30; done
log 'final: судья для Dify'
poetry run python -m benchmarks.judge_answers domain:full naive:vector dify:dify_vector \
    dify:dify_hybrid_rerank >>"$LOGS/judge.log" 2>&1
log "final: судья завершён с кодом $?"
poetry run python -m benchmarks.plots >>"$LOGS/final.log" 2>&1
poetry run python -m benchmarks.compare_subset >>"$LOGS/final.log" 2>&1
log "final: сравнение на подмножестве завершено с кодом $?"
