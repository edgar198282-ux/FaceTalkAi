#!/usr/bin/env bash
set -euo pipefail
export MUSETALK_DIR="${MUSETALK_DIR:-/workspace/MuseTalk}"
export LIVEPORTRAIT_DIR="${LIVEPORTRAIT_DIR:-/workspace/LivePortrait}"
export FACETALK_WORK_DIR="${FACETALK_WORK_DIR:-/workspace/facetalk_jobs}"
mkdir -p "$FACETALK_WORK_DIR"
exec uvicorn worker:APP --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
