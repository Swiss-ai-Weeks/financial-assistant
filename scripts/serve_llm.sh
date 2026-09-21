#!/usr/bin/env bash
#
# Serve Nemotron 3.5 Lightning 30B-A3B on the two H100s.
#
# Topology: one full BF16 replica per GPU (data parallel),
# behind ONE OpenAI-compatible endpoint. The weights (~60 GB)
# fit a single 80 GB H100, and an investigation is a fan-out
# of independent requests, so two replicas double throughput
# with no tensor-parallel communication. See docs/MODEL.md.
#
#   LLM_TOPOLOGY=replicas   one replica per GPU (default)
#   LLM_TOPOLOGY=sharded    one model split over both GPUs:
#                           more KV cache for very long context
#
# Kernel-level tuning flags recommended by the model card for
# your vLLM version can be appended through VLLM_EXTRA_ARGS.

set -euo pipefail

# vLLM is installed into the project's virtualenv by
# setup_gpu_box.sh. Use that copy whether or not the venv is
# activated; fall back to whatever is on PATH.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -x "$ROOT/.venv/bin/vllm" ]; then
  VLLM="$ROOT/.venv/bin/vllm"
elif command -v vllm >/dev/null 2>&1; then
  VLLM="vllm"
else
  echo "vllm not found. Install it with: $ROOT/.venv/bin/pip install -U vllm" >&2
  exit 127
fi

# FlashInfer's sampler compiles a kernel the first time it is
# used, which needs the CUDA toolkit (nvcc). A box with only the
# driver, such as the hackathon instance, fails at warm-up with
# "Could not find nvcc". vLLM's own sampler needs nothing.
if ! command -v nvcc >/dev/null 2>&1 && [ ! -x "${CUDA_HOME:-/usr/local/cuda}/bin/nvcc" ]; then
  export VLLM_USE_FLASHINFER_SAMPLER="${VLLM_USE_FLASHINFER_SAMPLER:-0}"
fi

MODEL="${LLM_MODEL:-nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16}"
PORT="${LLM_PORT:-8000}"
TOPOLOGY="${LLM_TOPOLOGY:-replicas}"
MAX_MODEL_LEN="${LLM_MAX_MODEL_LEN:-65536}"

case "$TOPOLOGY" in
  replicas) PARALLELISM=(--data-parallel-size 2) ;;
  sharded)  PARALLELISM=(--tensor-parallel-size 2) ;;
  single)   PARALLELISM=() ;;
  *) echo "LLM_TOPOLOGY must be replicas, sharded or single" >&2; exit 1 ;;
esac

# Every stage shares a long system prompt across many requests,
# which is exactly what prefix caching accelerates.
exec "$VLLM" serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --trust-remote-code \
  --max-model-len "$MAX_MODEL_LEN" \
  --max-num-seqs 128 \
  --gpu-memory-utilization 0.90 \
  --enable-prefix-caching \
  ${PARALLELISM[@]+"${PARALLELISM[@]}"} \
  ${VLLM_EXTRA_ARGS:-}
