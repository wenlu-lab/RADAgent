#!/usr/bin/env bash
# Launch vLLM serving Qwen3-Coder 30B-A3B Instruct (FP8) for the GBS agent.
# Idempotent: if vLLM is already responding on the port, exits successfully.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VLLM_BIN="${REPO}/.venv/bin/vllm"

PORT="${GBS_VLLM_PORT:-8000}"
HOST="${GBS_VLLM_HOST:-127.0.0.1}"
MODEL="Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8"
SERVED_NAME="qwen3-coder"

# Idempotency check
if curl -sf "http://${HOST}:${PORT}/v1/models" > /dev/null 2>&1; then
    echo "vLLM already responding on http://${HOST}:${PORT}" >&2
    exit 0
fi

if [ ! -x "$VLLM_BIN" ]; then
    echo "vLLM binary not found at $VLLM_BIN — run venv setup first" >&2
    exit 1
fi

echo "Starting vLLM serve for ${MODEL} on http://${HOST}:${PORT}" >&2

# Note: --kv-cache-dtype fp8 is intentionally NOT set. The Triton attention
# kernels in vLLM 0.10.1 require fp8e4nv (Hopper/Ada native FP8) for FP8 KV
# cache, which an A100 (Ampere) does not have. The model weights are still
# FP8 — vLLM's Marlin kernel upcasts them to BF16 for compute on A100.
# KV cache stays BF16 (~2x size of FP8 cache, but we have 80GB).
exec "$VLLM_BIN" serve "${MODEL}" \
    --host "${HOST}" --port "${PORT}" \
    --max-model-len 262144 \
    --enable-auto-tool-choice \
    --tool-call-parser qwen3_coder \
    --gpu-memory-utilization 0.92 \
    --served-model-name "${SERVED_NAME}"
