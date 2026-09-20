# Model choice: Nemotron 3.5 Lightning 30B-A3B on 2 × H100

The hackathon gives us two NVIDIA H100 80 GB GPUs on HPE infrastructure. This
note explains which model we serve on them, how, and why.

## What the model is asked to do

The language model is never asked whether an explanation is *true*. One
investigation is a fan-out of narrow, structured tasks:

| Stage | Calls | Task |
|---|---|---|
| Claim extraction | one per article | atomic claims, each with a verbatim source quote |
| Hypothesis generation | 1 | competing explanations for the anomaly |
| Hypothesis audit | 1 | premises each explanation silently assumes |
| Relation assessment | one per hypothesis | supports / contradicts / weakens / context, per claim |
| Causal triage (discovery) | one per unusual relationship | is there an event behind the move, does it last, which headline says so |

Triage is the clearest case for this model. Discovery finds a handful of
unusual relationships per scan and every one needs a reading before it can be
ranked, so the stage must be cheap enough to run on all of them: headlines and
summaries only, no article fetch, one short JSON answer. It is a filter, not a
judgement. A lasting, company-specific event means the gap is a repricing and
the candidate is dropped; the full ClaimGraph is reserved for what survives.

Everything else is deterministic code: which news is admissible (published
before the anomaly's evidence cutoff), quote verification (the quote must occur
literally in the article), verdict tallies and the ClaimGraph. For triage, code
checks that the cited headline is one that was offered and was published
before the anomaly; an answer that fails is discarded, never repaired, and
nothing is dropped when the model is offline.

So the workload is **many short, independent, JSON-constrained requests over
long inputs**. That profile, not leaderboard rank, drives the choice.

## Why Nemotron 3.5 Lightning 30B-A3B

1. **3B active parameters of 30B (mixture of experts).** Per-token compute is
   that of a small model, while capacity is that of a mid-sized one. An
   investigation is 10–20 calls; throughput is what the portfolio manager feels.
2. **Hybrid Mamba-2 + attention.** State-space layers keep memory flat in
   sequence length, so whole articles go in the prompt instead of snippets. The
   cause of a move is often one sentence deep in a filing.
3. **Reasoning is switchable per request.** Extraction is precise and shallow:
   thinking tokens add latency, not accuracy. Every stage runs with
   `enable_thinking: false` (`LLM_THINKING_CONTROL=chat_template`). The flag is
   per request, so a future stage can turn it on.
4. **Open weights, commercially usable, served by us.** Holdings and the
   questions asked about them never leave the machine. Only public market data
   and public news come in.
5. **Recommended by the hackathon instructors** for exactly this hardware.

## Serving topology

BF16 weights are about 60 GB, so **one H100 holds a complete replica** with
~12 GB left for KV cache and activations at `--gpu-memory-utilization 0.90`.

```
                 ┌──────────────── vLLM, one OpenAI-compatible endpoint :8000 ────────────────┐
  desk API ───►  │   GPU 0 · replica A (BF16)            GPU 1 · replica B (BF16)             │
                 └─────────────────────── --data-parallel-size 2 ─────────────────────────────┘
```

We run **two replicas (data parallel)** rather than one model sharded over both
GPUs (tensor parallel):

- requests are independent, so replicas scale throughput ~linearly;
- no per-layer all-reduce between GPUs on every token;
- one replica keeps serving if the other is restarted.

Tensor parallel (`LLM_TOPOLOGY=sharded`) is the better choice only when a single
request needs more KV cache than one GPU has left, i.e. very long contexts. Our
documents are capped at 6 000 characters per call, far below that.

`--enable-prefix-caching` matters here: each stage sends the same long system
prompt with every request, and the relation stage repeats the full claim list
once per hypothesis.

The NVFP4 checkpoints of this model target Blackwell GPUs. On Hopper (H100) we
serve BF16.

## Running it

```bash
pip install vllm                 # on the GPU box; use the version the model card names
make llm                         # scripts/serve_llm.sh, port 8000
```

or containerised:

```bash
docker compose -f infra/docker-compose.yml --profile gpu up -d vllm
```

The model card lists additional kernel-level flags for the Mamba layers that
depend on the vLLM version. Append them with `VLLM_EXTRA_ARGS="..."` rather than
editing the script. Model card:
<https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16>

Check it from the desk: the **NEMOTRON** pill in the top bar turns green, and
the Model page (chip icon in the left rail) shows measured per-stage latency of
the last investigation.

## Without GPUs

The provider is any OpenAI-compatible endpoint. For development, point the desk
at the same model hosted by NVIDIA:

```bash
LLM_PROVIDER=nvidia-nim
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
LLM_API_KEY=nvapi-...
```

Charts, anomalies, pair scans and news work with no model at all. Only the
**Explain** button needs one.

## What we would measure next

- per-stage latency and tokens/s, replicas vs sharded, from the stage timings
  the API already records on every investigation;
- quote-verification failure rate (how often the model paraphrases instead of
  quoting), by prompt version;
- agreement of relation assessments across repeated runs at temperature 0.
