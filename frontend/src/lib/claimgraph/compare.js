/*
 * The same anomaly explained by different models.
 *
 * Nothing here ranks a model. It lines up what each one
 * produced from the SAME admissible evidence, and says where
 * their explanations overlap: agreement between Nemotron and
 * Apertus means the explanation does not depend on who was
 * asked. Disagreement is where a person should look.
 */

const STOPWORDS = new Set(
  (
    "the a an and or of to in on for with by from at as is are was were be " +
    "its their that this which may might could would stock price shares " +
    "company move moved because due"
  ).split(" ")
);

export function tokens(text) {
  return new Set(
    String(text ?? "")
      .toLowerCase()
      .match(/[a-z][a-z0-9]{2,}/g)
      ?.filter((word) => !STOPWORDS.has(word)) ?? []
  );
}

/** Jaccard overlap of the meaningful words of two explanations. */
export function similarity(a, b) {
  const left = tokens(a);
  const right = tokens(b);

  if (!left.size || !right.size) return 0;

  let shared = 0;

  left.forEach((word) => {
    if (right.has(word)) shared += 1;
  });

  return shared / (left.size + right.size - shared);
}

export const MATCH_THRESHOLD = 0.3;

function seconds(run) {
  if (!run.finished_at) return null;

  return (Date.parse(run.finished_at) - Date.parse(run.created_at)) / 1000;
}

function graphCount(run, ...kinds) {
  return (run.graph?.nodes ?? []).filter((node) => kinds.includes(node.kind)).length;
}

/** One column of the comparison. */
export function summarize(run) {
  const best = run.hypotheses?.[0] ?? null;

  return {
    investigation_id: run.investigation_id,
    model_id: run.model_id ?? "default",
    label: run.model_label || run.model.split("/").pop(),
    model: run.model,
    local: run.model_local,
    status: run.status,
    error: run.error,
    created_at: run.created_at,
    seconds: seconds(run),
    calls: run.usage?.calls ?? 0,
    prompt_tokens: run.usage?.prompt_tokens ?? 0,
    completion_tokens: run.usage?.completion_tokens ?? 0,
    documents: run.documents_used,
    claims: run.claims?.length ?? 0,
    hypotheses: run.hypotheses ?? [],
    best,
    supporting: (run.hypotheses ?? []).reduce((n, h) => n + h.supporting, 0),
    countering: (run.hypotheses ?? []).reduce(
      (n, h) => n + h.contradicting + h.weakening,
      0
    ),
    gaps: graphCount(run, "missing_evidence", "evidence_requirement"),
    sec: graphCount(run, "calculation"),
    followups: run.followups?.length ?? 0,
    has_graph: run.graph != null,
  };
}

/**
 * Investigations grouped by anomaly, newest first. Within an
 * anomaly only the latest finished run of each model counts,
 * so explaining again replaces rather than duplicates.
 */
export function comparisons(investigations) {
  const groups = new Map();

  [...(investigations ?? [])]
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    .forEach((run) => {
      const id = run.anomaly.anomaly_id;

      if (!groups.has(id)) groups.set(id, { anomaly: run.anomaly, runs: new Map() });

      const runs = groups.get(id).runs;
      const key = run.model_id ?? "default";
      const known = runs.get(key);

      // Prefer a completed run over a newer failed one.
      if (!known || (known.status !== "completed" && run.status === "completed")) {
        runs.set(key, run);
      }
    });

  return [...groups.values()].map(({ anomaly, runs }) => {
    const columns = [...runs.values()].map(summarize);

    return { anomaly, columns, agreement: agreement(columns) };
  });
}

/**
 * For every explanation of the first model, the closest one of
 * each other model, and whether both rank it as best supported.
 */
export function agreement(columns) {
  const done = columns.filter((c) => c.status === "completed" && c.hypotheses.length);

  if (done.length < 2) return null;

  const [reference, ...others] = done;

  const rows = reference.hypotheses.map((hypothesis) => ({
    text: hypothesis.text,
    score: hypothesis.score,
    matches: others.map((other) => {
      const closest = other.hypotheses
        .map((candidate) => ({
          candidate,
          overlap: similarity(hypothesis.text, candidate.text),
        }))
        .sort((a, b) => b.overlap - a.overlap)[0];

      return closest && closest.overlap >= MATCH_THRESHOLD
        ? {
            model_id: other.model_id,
            text: closest.candidate.text,
            score: closest.candidate.score,
            overlap: closest.overlap,
          }
        : { model_id: other.model_id, text: null, score: null, overlap: closest?.overlap ?? 0 };
    }),
  }));

  const sameBest = others.every(
    (other) =>
      similarity(reference.best?.text, other.best?.text) >= MATCH_THRESHOLD
  );

  const shared = rows.filter((row) => row.matches.every((m) => m.text != null)).length;

  return {
    reference: reference.model_id,
    rows,
    same_best: sameBest,
    shared,
    total: rows.length,
  };
}

/**
 * Display order: the anomaly in focus, then anomalies read by
 * at least two models, then the rest. The incoming order
 * (newest first) is kept inside each band.
 */
export function arrange(groups, focusAnomalyId = null) {
  const band = (group) => {
    if (focusAnomalyId != null && group.anomaly.anomaly_id === focusAnomalyId) return 0;

    return group.columns.length >= 2 ? 1 : 2;
  };

  return groups
    .map((group, index) => ({ group, index }))
    .sort((a, b) => band(a.group) - band(b.group) || a.index - b.index)
    .map(({ group }) => group);
}

/**
 * Configured analysis models that have not read this anomaly
 * yet. A run stored without a model id was read by the default
 * model.
 */
export function candidates(modelList, columns) {
  const taken = new Set(columns.map((column) => column.model_id));

  if (taken.has("default") && modelList?.default_id) taken.add(modelList.default_id);

  return (modelList?.models ?? []).filter(
    (model) =>
      (model.roles ?? []).includes("analysis") &&
      !taken.has(model.id) &&
      !(model.default && taken.has("default"))
  );
}

/** How many models an agreement compares, the reference included. */
export function readers(result) {
  return result ? (result.rows[0]?.matches.length ?? 0) + 1 : 0;
}
