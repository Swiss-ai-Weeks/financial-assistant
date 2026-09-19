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
exec vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --trust-remote-code \
  --max-model-len "$MAX_MODEL_LEN" \
  --max-num-seqs 128 \
  --gpu-memory-utilization 0.90 \
  --enable-prefix-caching \
  "${PARALLELISM[@]}" \
  ${VLLM_EXTRA_ARGS:-}
