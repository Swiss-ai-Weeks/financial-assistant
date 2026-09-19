import { dateTime } from "../../lib/format";
import { ExternalIcon } from "../icons";

/** Every claim carries the exact sentence it was extracted from. */
export default function ClaimList({ claims }) {
  return (
    <div className="claims">
      {claims.map((claim) => (
        <article key={claim.claim_id} className="claim">
          <div className="claim__type eyebrow">
            {claim.claim_type.replaceAll("_", " ")}
          </div>
          <p className="claim__text">{claim.text}</p>
          <blockquote className="claim__quote">“{claim.source_quote}”</blockquote>
          <a
            className="claim__source mono"
            href={claim.url}
            target="_blank"
            rel="noreferrer"
          >
            {claim.publisher ?? "Source"}
            {claim.published_at && ` · ${dateTime(claim.published_at)} UTC`}
            <ExternalIcon size={12} />
          </a>
        </article>
      ))}
    </div>
  );
}
