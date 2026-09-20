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
make serve   # the desk, on one port (see step 3)
make warm    # once
```

If the weights are gated, `huggingface-cli login` first. If `make llm` rejects a
flag, the installed vLLM is older than the model card expects: upgrade vLLM, or
pass the card's flags through `VLLM_EXTRA_ARGS`.

## 3. Open it

**The machine is opened in a browser (VS Code web, NVIDIA Launchpad).** Plain
`ssh` from a laptop does not work: the hostname only resolves inside. Run the
desk on ONE port, with the UI pre-built and served by the API:

```bash
make serve        # prints the port it took, e.g. 8081
```

then in VS Code: **PORTS** tab -> *Forward a Port* -> that port -> globe icon.
The desk is served with relative paths, so it works under a forwarding prefix
such as `/proxy/8081/`. `make dev` does not: its hot-reload server assumes it
owns the host root, and the forwarded URL answers 404.

**The machine is reached over SSH.** Either mode works:

```bash
ssh -L 8081:localhost:8081 <user>@<gpu-host>      # then http://localhost:8081
```

Ports: on the hackathon box 8080 is the instance's own shell gateway
(`openshell-gateway`, do not stop it) and 5173 is another team member's app.
`make dev` and `make serve` both take the first free port and print it.

## 4. Optional keys on the instance

`FINNHUB_API_KEY` in `~/pythia/.env` is only needed to download *more* news
(`make news`); the archive in the tarball already covers the demo window.

## Later updates

Re-create the bundle on the laptop, copy it over, run the script again: it
fast-forwards the existing checkout.
