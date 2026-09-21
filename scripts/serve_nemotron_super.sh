#!/usr/bin/env bash
#
# Bring up Llama-3.3-Nemotron-Super 49B as a THIRD model, next
# to Lightning (its own GPU) and Apertus, so the same anomaly
# can be read by all three.
#
# It runs as an NVIDIA NIM container on port 8000, on the GPU
# with the most free memory, and is told to take only a share
# of that card: by default a NIM claims 90% of it, which fails
# as soon as Apertus is already there. The key, the user and
# the weights folder are copied from the Lightning container,
# which is the same kind of container and already works.
#
#   make super49b                         start (or restart) it
#   SUPER49B_GPU_MEMORY=0.66 make super49b
#
# Then, in .env, the desk learns about it through PYTHIA_MODELS
# (see .env.example) and is restarted.

set -euo pipefail

NAME="${SUPER49B_NAME:-claimgraph-nim}"
IMAGE="${SUPER49B_IMAGE:-nvcr.io/nim/nvidia/llama-3.3-nemotron-super-49b-v1.5:2.0.12}"
PORT="${SUPER49B_PORT:-8000}"
MEMORY="${SUPER49B_GPU_MEMORY:-0.70}"
MAX_MODEL_LEN="${SUPER49B_MAX_MODEL_LEN:-32768}"
SIBLING="${SUPER49B_COPY_FROM:-claimgraph-nim-lightning}"

command -v docker >/dev/null || { echo "docker not found" >&2; exit 1; }

# The freest GPU, and whether the share asked for fits on it. A
# NIM that does not fit only says so a minute later, at the end
# of a long traceback.
read -r GPU FREE_MIB TOTAL_MIB < <(
  nvidia-smi --query-gpu=index,memory.free,memory.total --format=csv,noheader,nounits \
    ${SUPER49B_GPU:+--id="$SUPER49B_GPU"} | tr -d ',' | sort -k2 -n -r | head -1
)

NEEDED_MIB="$(awk -v m="$MEMORY" -v t="$TOTAL_MIB" 'BEGIN { printf "%d", m * t }')"

if [ "$FREE_MIB" -lt "$NEEDED_MIB" ]; then
  echo "GPU $GPU is the freest and has ${FREE_MIB} MiB free; a share of $MEMORY needs ${NEEDED_MIB} MiB." >&2
  echo "What is holding the GPUs:" >&2
  nvidia-smi --query-compute-apps=pid,used_memory,name --format=csv,noheader >&2 || true
  echo >&2
  echo "Usually that is Apertus started with the whole card. Stop it (Ctrl-C in its pane)," >&2
  echo "run 'make apertus' again (it now takes ~24 GB), then 'make super49b'." >&2
  echo "The 49B needs about 57 GB for its weights: a share below ~0.64 will not load." >&2
  exit 1
fi

# An existing container of that name is simply started again:
# its settings (memory share included) are kept.
if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
  if [ "${SUPER49B_RECREATE:-0}" = "1" ]; then
    docker rm -f "$NAME" >/dev/null
  else
    docker start "$NAME" >/dev/null
    echo "Started the existing container $NAME (SUPER49B_RECREATE=1 to rebuild it)."
    echo "Follow it with: docker logs -f $NAME"
    exit 0
  fi
fi

docker inspect "$SIBLING" >/dev/null 2>&1 || {
  echo "Container $SIBLING not found: set SUPER49B_COPY_FROM to a working NIM container," >&2
  echo "or export NGC_API_KEY and SUPER49B_CACHE yourself." >&2
  [ -n "${NGC_API_KEY:-}" ] || exit 1
}

# Never printed.
if [ -z "${NGC_API_KEY:-}" ]; then
  NGC_API_KEY="$(docker inspect "$SIBLING" --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^NGC_API_KEY=//p')"
  export NGC_API_KEY
fi

[ -n "$NGC_API_KEY" ] || { echo "No NGC_API_KEY found in $SIBLING; export it and run again." >&2; exit 1; }

RUN_AS="$(docker inspect "$SIBLING" --format '{{.Config.User}}' 2>/dev/null || true)"
CACHE="${SUPER49B_CACHE:-$(docker inspect "$SIBLING" --format '{{range .Mounts}}{{if eq .Destination "/opt/nim/.cache"}}{{.Source}}{{end}}{{end}}' 2>/dev/null || true)}"

[ -n "$CACHE" ] || { echo "Could not find the NIM cache folder; set SUPER49B_CACHE." >&2; exit 1; }

echo "Starting $NAME on GPU $GPU, port $PORT, memory share $MEMORY"

docker run -d --name "$NAME" \
  --gpus "\"device=$GPU\"" --shm-size=16g \
  ${RUN_AS:+-u "$RUN_AS"} \
  -e NGC_API_KEY \
  -e NIM_MAX_MODEL_LEN="$MAX_MODEL_LEN" \
  -v "$CACHE:/opt/nim/.cache" \
  -p "127.0.0.1:$PORT:8000" \
  "$IMAGE" \
  --gpu-memory-utilization "$MEMORY" >/dev/null

cat <<DONE

Loading takes a few minutes (the weights are already on disk):

  docker logs -f $NAME          # until "Application startup complete"
  curl -s localhost:$PORT/v1/models | python3 -m json.tool | grep '"id"' | head -1

Use that id as "model" in the PYTHIA_MODELS line of .env, then restart the desk.
DONE
