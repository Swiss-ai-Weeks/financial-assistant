import { MATCH_THRESHOLD } from "../../lib/claimgraph/compare";
import { signed } from "../../lib/format";

function share(overlap) {
  return `${Math.round(overlap * 100)}%`;
}

function Counterpart({ match, column }) {
  if (match.text == null) {
    return (
      <td className="compare__cell">
        <span className="muted">no counterpart</span>
        <span className="compare__cell-meta mono muted">
          closest {share(match.overlap)}
        </span>
      </td>
    );
  }

  const rankedFirst = column?.best?.text === match.text;

  return (
    <td className="compare__cell">
      <p>{match.text}</p>
      <span className="compare__cell-meta mono">
        <span className="compare__overlap">{share(match.overlap)} overlap</span>
        <span className="muted">score {signed(match.score)}</span>
        {rankedFirst && <span className="muted">ranked first</span>}
      </span>
    </td>
  );
}

/**
 * The reference model's explanations, each next to the closest
 * explanation of every other model.
 */
export default function CompareAlignment({ agreement, columns }) {
  const byModel = new Map(columns.map((column) => [column.model_id, column]));
  const reference = byModel.get(agreement.reference);
  const others = agreement.rows[0]?.matches.map((match) => byModel.get(match.model_id)) ?? [];

  return (
    <div className="compare__alignment">
      <span className="eyebrow">Explanation alignment</span>

      <div className="compare__scroll">
        <table className="compare__table">
          <thead>
            <tr>
              <th>
                {reference?.label ?? agreement.reference}
                <small> · reference</small>
              </th>
              {others.map((column, index) => (
                <th key={column?.model_id ?? index}>
                  {column?.label ?? "Model"}
                  <small> · closest explanation</small>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {agreement.rows.map((row, index) => (
              <tr key={`${index}-${row.text}`}>
                <td className="compare__cell">
                  <p>{row.text}</p>
                  <span className="compare__cell-meta mono muted">
                    score {signed(row.score)}
                    {index === 0 && " · ranked first"}
                  </span>
                </td>
                {row.matches.map((match, position) => (
                  <Counterpart
                    key={match.model_id}
                    match={match}
                    column={others[position]}
                  />
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="compare__note muted">
        Overlap is the share of meaningful words two explanations have in common.
        Under {share(MATCH_THRESHOLD)} they count as different explanations.
      </p>
    </div>
  );
}
