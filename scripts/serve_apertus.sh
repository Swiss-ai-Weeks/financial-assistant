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
#                      BF16. It is a small neighbour: unless told
#                      otherwise it goes on whichever GPU has the
#                      most free memory and takes ~24 GB of it,
#                      not a share of the whole card, so it fits
#                      next to a Nemotron that is already there.
#                      Override with CUDA_VISIBLE_DEVICES and
#                      APERTUS_GPU_MEMORY (a fraction of the card).
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

SIZE="${APERTUS_SIZE:-8b}"
PORT="${APERTUS_PORT:-8001}"
MAX_MODEL_LEN="${APERTUS_MAX_MODEL_LEN:-32768}"

case "$SIZE" in
  8b)
    MODEL="${APERTUS_MODEL:-swiss-ai/Apertus-8B-Instruct-2509}"
    PARALLELISM=()
    MAX_MODEL_LEN="${APERTUS_MAX_MODEL_LEN:-16384}"

    # Weights (~16 GB) plus KV cache for 16k tokens of context.
    BUDGET_MIB="${APERTUS_BUDGET_MIB:-24576}"

    if command -v nvidia-smi >/dev/null 2>&1; then
      # index, free MiB, total MiB of the GPU with the most room
      # (of the one that was chosen, when one was).
      read -r GPU FREE_MIB TOTAL_MIB < <(
        nvidia-smi --query-gpu=index,memory.free,memory.total \
          --format=csv,noheader,nounits \
          ${CUDA_VISIBLE_DEVICES:+--id="$CUDA_VISIBLE_DEVICES"} \
          | tr -d ',' | sort -k2 -n -r | head -1
      )

      export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-$GPU}"

      if [ -z "${APERTUS_GPU_MEMORY:-}" ] && [ "$FREE_MIB" -lt "$BUDGET_MIB" ]; then
        echo "GPU $GPU has the most free memory and that is only ${FREE_MIB} MiB;" >&2
        echo "Apertus 8B needs about ${BUDGET_MIB} MiB. Free a GPU (nvidia-smi shows" >&2
        echo "who holds it) or use the hosted profile: APERTUS_PROFILE=hosted." >&2
        exit 1
      fi

      # vLLM takes a fraction of the WHOLE card.
      DEFAULT_MEMORY="$(awk -v b="$BUDGET_MIB" -v t="$TOTAL_MIB" 'BEGIN { printf "%.2f", b / t }')"
      echo "GPU $CUDA_VISIBLE_DEVICES: ${FREE_MIB} MiB free of ${TOTAL_MIB}"
    else
      DEFAULT_MEMORY="0.85"
    fi

    MEMORY="${APERTUS_GPU_MEMORY:-$DEFAULT_MEMORY}"
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

echo "Serving $MODEL on :$PORT (GPU ${CUDA_VISIBLE_DEVICES:-all}, memory fraction $MEMORY)"
echo "The desk must be started with APERTUS_PROFILE=local and APERTUS_MODEL=$MODEL"

exec "$VLLM" serve "$MODEL" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --max-model-len "$MAX_MODEL_LEN" \
  --max-num-seqs 64 \
  --gpu-memory-utilization "$MEMORY" \
  --enable-prefix-caching \
  ${PARALLELISM[@]+"${PARALLELISM[@]}"} \
  ${QUANTIZATION[@]+"${QUANTIZATION[@]}"} \
  ${VLLM_EXTRA_ARGS:-}
