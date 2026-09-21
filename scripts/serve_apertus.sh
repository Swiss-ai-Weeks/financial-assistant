#!/usr/bin/env bash
#
# Serve Apertus, the Swiss AI Initiative's fully open model
# (EPFL, ETH Zurich, CSCS), next to Nemotron so the same anomaly
# can be explained by both and the ClaimGraphs compared.
#
# Nemotron keeps port 8000. Apertus takes 8001, which is where
# APERTUS_PROFILE=local expects it.
#
#   APERTUS_SIZE=8b    (default) Apertus-8B-Instruct, ~16 GB in
#                      BF16. Shares GPU 1 with a Nemotron
#                      replica: start Nemotron with
#                        LLM_TOPOLOGY=single CUDA_VISIBLE_DEVICES=0 make llm
#                      or leave both replicas up and give this
#                      one a smaller memory share (the default
#                      below assumes the GPU is otherwise free).
#
#   APERTUS_SIZE=70b   Apertus-70B-Instruct. BF16 weights are
#                      ~140 GB, so it needs BOTH H100s (tensor
#                      parallel) and Nemotron cannot run at the
#                      same time. Set APERTUS_QUANTIZATION=fp8
#                      to fit it on the two cards with room for
#                      KV cache, or on one card without Nemotron.
#
# Requires vLLM with transformers >= 4.56 (Apertus support).

set -euo pipefail

SIZE="${APERTUS_SIZE:-8b}"
PORT="${APERTUS_PORT:-8001}"
MAX_MODEL_LEN="${APERTUS_MAX_MODEL_LEN:-32768}"

case "$SIZE" in
  8b)
    MODEL="${APERTUS_MODEL:-swiss-ai/Apertus-8B-Instruct-2509}"
    export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-1}"
    PARALLELISM=()
    MEMORY="${APERTUS_GPU_MEMORY:-0.85}"
    ;;
  70b)
    MODEL="${APERTUS_MODEL:-swiss-ai/Apertus-70B-Instruct-2509}"
    PARALLELISM=(--tensor-parallel-size "${APERTUS_TENSOR_PARALLEL:-2}")
    MEMORY="${APERTUS_GPU_MEMORY:-0.92}"
    ;;
  *) echo "APERTUS_SIZE must be 8b or 70b" >&2; exit 1 ;;
esac

QUANTIZATION=()

if [ -n "${APERTUS_QUANTIZATION:-}" ]; then
  QUANTIZATION=(--quantization "$APERTUS_QUANTIZATION")
fi

echo "Serving $MODEL on :$PORT"
echo "The desk must be started with APERTUS_PROFILE=local and APERTUS_MODEL=$MODEL"

exec vllm serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --max-model-len "$MAX_MODEL_LEN" \
  --max-num-seqs 64 \
  --gpu-memory-utilization "$MEMORY" \
  --enable-prefix-caching \
  "${PARALLELISM[@]}" \
  "${QUANTIZATION[@]}" \
  ${VLLM_EXTRA_ARGS:-}
