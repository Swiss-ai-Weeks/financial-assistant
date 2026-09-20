#!/usr/bin/env bash
#
# Set Pythia up on the GPU instance, from the two files copied
# off a laptop (see docs/DEPLOY_GPU.md):
#
#   pythia.bundle     the code, as a git bundle
#   pythia-data.tgz   news archive + price and analogue caches
#
# Usage, from the directory holding both files:
#
#   bash setup_gpu_box.sh
#
# Safe to run again: it updates an existing checkout.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TARGET="${PYTHIA_DIR:-$HOME/pythia}"
BRANCH="feat/trading-desk-ui"

[[ -f "$HERE/pythia.bundle" ]] || { echo "pythia.bundle not found next to this script" >&2; exit 1; }

echo "== GPUs"
nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader || {
  echo "nvidia-smi failed: this does not look like the GPU instance." >&2; exit 1; }

echo "== Code -> $TARGET"
if [[ -d "$TARGET/.git" ]]; then
  git -C "$TARGET" fetch "$HERE/pythia.bundle" "$BRANCH"
  git -C "$TARGET" checkout "$BRANCH"
  git -C "$TARGET" merge --ff-only FETCH_HEAD
else
  git clone -b "$BRANCH" "$HERE/pythia.bundle" "$TARGET"
fi

cd "$TARGET"

if [[ -f "$HERE/pythia-data.tgz" ]]; then
  echo "== Data (news archive, caches)"
  tar -xzf "$HERE/pythia-data.tgz"
fi

echo "== Dependencies"
make setup

# Local inference is the whole point of this machine.
if grep -q '^LLM_PROFILE=' .env; then
  sed -i.bak 's/^LLM_PROFILE=.*/LLM_PROFILE=local/' .env && rm -f .env.bak
else
  echo 'LLM_PROFILE=local' >> .env
fi

.venv/bin/pip install -q vllm

cat <<DONE

Ready in $TARGET. Three terminals (tmux recommended):

  1)  make llm      # Nemotron, one replica per H100, port 8000.
                    # First start downloads ~60 GB of weights.
  2)  make dev      # API :8080, UI :5173
  3)  make warm     # once: pre-builds the slow caches

Open the UI from your laptop:

  ssh -L 5173:localhost:5173 -L 8080:localhost:8080 <user>@<this-host>
  -> http://localhost:5173

Before recording:  make forget-runs   (drops answers made by the hosted model)
Afterwards:        make runs          (proves every saved run was produced locally)
DONE
