import { useMemo } from "react";

import { arrange, comparisons } from "../../lib/claimgraph/compare";
import CompareModels from "./CompareModels";
import CompareSection from "./CompareSection";

// Beyond these, a single-model anomaly starts folded.
const OPEN_BY_DEFAULT = 3;

/**
 * The same anomaly explained by several models, side by side.
 * It shows where they agree; it does not rank them.
 */
export default function CompareView({
  investigations,
  models,
  focusAnomalyId = null,
  onOpen,
  onExplain,
}) {
  const groups = useMemo(
    () => arrange(comparisons(investigations), focusAnomalyId),
    [investigations, focusAnomalyId]
  );

  const runs = useMemo(
    () => new Map((investigations ?? []).map((run) => [run.investigation_id, run])),
    [investigations]
  );

  return (
    <div className="compare">
      <header className="compare__hero">
        <span className="eyebrow">ClaimGraph · model comparison</span>
        <h1>Same evidence, different readers.</h1>
        <p>
          Every model reads the same point-in-time news and SEC figures. When they
          agree, the explanation does not depend on who was asked; where they
          differ is where a person should look. Nothing here ranks a model.
        </p>
      </header>

      <CompareModels models={models} />

      {groups.length === 0 ? (
        <div className="empty compare__empty">
          <span className="eyebrow">
            {investigations == null ? "Loading investigations…" : "Nothing to compare yet"}
          </span>
          <p>
            Select an anomaly on the desk and ask a model to explain it. Then run
            the same anomaly again with another model: both readings appear here,
            side by side, with the explanations they share.
          </p>
        </div>
      ) : (
        groups.map((group, index) => (
          <CompareSection
            key={group.anomaly.anomaly_id}
            group={group}
            runs={runs}
            models={models}
            focused={group.anomaly.anomaly_id === focusAnomalyId}
            defaultOpen={group.columns.length >= 2 || index < OPEN_BY_DEFAULT}
            onOpen={onOpen}
            onExplain={onExplain}
          />
        ))
      )}
    </div>
  );
}
