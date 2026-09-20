import { useMemo } from "react";

const REASONS = [
  {
    title: "3B active parameters out of 30B",
    text:
      "A mixture-of-experts model only runs a fraction of its weights per token. " +
      "Explaining one anomaly takes 10–20 model calls (one per article, one per " +
      "explanation). Throughput decides whether a manager waits seconds or minutes.",
  },
  {
    title: "Hybrid Mamba-2 + attention, long context",
    text:
      "Full articles, not snippets, go into the prompt. The state-space layers keep " +
      "memory flat as documents get longer, so we never truncate the paragraph that " +
      "holds the actual cause.",
  },
  {
    title: "Fits one H100, so two H100s means two replicas",
    text:
      "BF16 weights are about 60 GB: one 80 GB H100 holds a full copy with room for " +
      "the KV cache. We run one replica per GPU behind a single endpoint instead of " +
      "splitting one model across both, doubling concurrent extractions with no " +
      "tensor-parallel communication.",
  },
  {
    title: "Reasoning can be switched off per request",
    text:
      "Claim extraction is a precise, shallow task: thinking tokens add latency and " +
      "no accuracy. Every stage runs with thinking disabled and JSON-constrained " +
      "output, and the structure is validated in code before anything is shown.",
  },
  {
    title: "Open weights, on our own GPUs",
    text:
      "Portfolio holdings and the questions a manager asks about them are sensitive. " +
      "Nothing leaves the machine: market data and public news come in, prompts " +
      "never go out.",
  },
];

const PIPELINE = [
  ["Deterministic", "Detect the anomaly, fix the evidence cutoff, select admissible news"],
  ["Nemotron × N articles", "Extract atomic claims, each with its exact source quote"],
  ["Nemotron × 1", "Generate competing explanations"],
  ["Nemotron × 1", "Audit each explanation for unsupported premises"],
  ["Nemotron × N explanations", "Weigh every claim against every explanation"],
  ["Deterministic", "Tally verdicts and build the ClaimGraph"],
  [
    "Nemotron × N candidates",
    "Discovery triage: is there an event behind each unusual relationship, and does it last",
  ],
  ["Deterministic", "Check the cited headline exists and predates the anomaly; drop repricings"],
];

export default function ModelPanel({ system, investigations }) {
  const timings = useMemo(() => {
    const latest = investigations?.find((run) => run.status === "completed");

    return latest?.stages ?? null;
  }, [investigations]);

  return (
    <div className="model">
      <header className="model__header">
        <span className="eyebrow">Inference · 2 × NVIDIA H100 80GB on HPE</span>
        <h1>Nemotron 3.5 Lightning 30B-A3B</h1>
        <p>
          The language model never decides what is true. It reads, extracts and
          proposes. Evidence rules, scoring and the graph are deterministic code.
          That division is why a small, fast, local model is the right one.
        </p>

        <div className="model__status mono">
          <span className={`dot ${system?.llm.online ? "dot--on" : "dot--off"}`} />
          <span>{system?.model}</span>
          <span className="muted">{system?.llm.detail}</span>
        </div>
      </header>

      <section className="model__topology">
        <div className="gpu">
          <span className="eyebrow">GPU 0 · H100</span>
          <strong>Replica A</strong>
          <span className="muted mono">BF16 · ~60 GB weights</span>
        </div>
        <div className="gpu">
          <span className="eyebrow">GPU 1 · H100</span>
          <strong>Replica B</strong>
          <span className="muted mono">BF16 · ~60 GB weights</span>
        </div>
        <div className="gpu gpu--endpoint">
          <span className="eyebrow">vLLM · data parallel = 2</span>
          <strong>One OpenAI-compatible endpoint</strong>
          <span className="muted mono">{system?.provider}</span>
        </div>
      </section>

      <section className="model__grid">
        {REASONS.map((reason) => (
          <article key={reason.title} className="reason">
            <h3>{reason.title}</h3>
            <p>{reason.text}</p>
          </article>
        ))}
      </section>

      <section className="model__pipeline">
        <span className="eyebrow">Where the model is called</span>
        <ol>
          {PIPELINE.map(([who, what]) => (
            <li key={what} className={who === "Deterministic" ? "" : "is-model"}>
              <span className="mono">{who}</span>
              <span>{what}</span>
            </li>
          ))}
        </ol>
      </section>

      {timings && (
        <section className="model__pipeline">
          <span className="eyebrow">Measured on the last investigation</span>
          <ol>
            {timings.map((stage) => (
              <li key={stage.key}>
                <span className="mono">{stage.seconds?.toFixed(1)}s</span>
                <span>
                  {stage.label} <small className="muted">{stage.detail}</small>
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
