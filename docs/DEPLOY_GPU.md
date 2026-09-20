# Running Pythia on the 2 × H100 instance

The laptop copy cannot be pushed to the team repository (read-only access), so
the code travels as a **git bundle**: one file that carries the whole branch
with its history and can be cloned from.

## 1. On the laptop

```bash
git bundle create /tmp/pythia-transfer/pythia.bundle feat/trading-desk-ui
tar -czf /tmp/pythia-transfer/pythia-data.tgz \
    data/archive/news data/cache/analogues data/cache/market

scp /tmp/pythia-transfer/pythia.bundle /tmp/pythia-transfer/pythia-data.tgz \
    scripts/setup_gpu_box.sh  <user>@<gpu-host>:~/
```

`.env` is deliberately not copied: it holds API keys. The data tarball is
optional but saves ~15 minutes of news download and ~7 of analogue building.

## 2. On the instance

```bash
bash ~/setup_gpu_box.sh
```

It checks the GPUs, clones the bundle into `~/pythia`, unpacks the data,
installs dependencies and vLLM, and sets `LLM_PROFILE=local`. Then, in tmux:

```bash
make llm     # serves Nemotron on both H100s; first start downloads ~60 GB
make dev     # API and UI
make warm    # once
```

If the weights are gated, `huggingface-cli login` first. If `make llm` rejects a
flag, the installed vLLM is older than the model card expects: upgrade vLLM, or
pass the card's flags through `VLLM_EXTRA_ARGS`.

## 3. From the laptop

```bash
ssh -L 5173:localhost:5173 -L 8080:localhost:8080 <user>@<gpu-host>
```

then open <http://localhost:5173>. The NEMOTRON pill turns green when vLLM is
up. No SSH (NVIDIA Launchpad)? Set `VITE_HMR_HOST=<public-hostname>` in
`frontend/.env` and use the Launchpad URL for port 5173.

## 4. Optional keys on the instance

`FINNHUB_API_KEY` in `~/pythia/.env` is only needed to download *more* news
(`make news`); the archive in the tarball already covers the demo window.

## Later updates

Re-create the bundle on the laptop, copy it over, run the script again: it
fast-forwards the existing checkout.
