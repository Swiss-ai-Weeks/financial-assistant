from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
import json

from pydantic import BaseModel, ConfigDict

from financial_assistant.domain import (
    AnomalyEvent,
    ExtractedClaim,
    Hypothesis,
    ModelOperation,
    ModelRun,
)

from .provider import StructuredLLM


PROMPT_VERSION = "hypothesis-generation-v2-fundamentals"


class _HypothesisCandidate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    text: str
    assumptions: tuple[str, ...] = ()


class _HypothesisResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    hypotheses: tuple[
        _HypothesisCandidate,
        ...
    ]


SYSTEM_PROMPT = """
Generate competing candidate explanations for a quantitative
market anomaly.

These are hypotheses to investigate, not conclusions.

The anomaly and supplied claims contain the only observations
you may treat as known, together with supplied application-calculated financial evidence.
Never calculate financial metrics yourself. Cite supplied calculation IDs. Financial
trends are descriptive context, not proof of causation.

Rules:

1. Return between 2 and 4 hypotheses.

2. Each hypothesis must represent a meaningfully distinct
   possible explanation for the anomaly.

3. State each hypothesis explicitly as uncertain using wording
   such as:
   - may reflect
   - could reflect
   - one possibility is
   - may be explained by

4. Do not introduce unsupported observations as facts.

5. In particular, do not assert any of the following unless
   explicitly present in the supplied anomaly or claims:
   - earnings or revenue beat/miss
   - analyst or market expectations
   - investor sentiment
   - trading volume
   - news volume or news tone
   - options activity
   - short interest
   - algorithmic or high-frequency trading activity
   - sector moves
   - macroeconomic moves

6. You may propose an unobserved mechanism as a hypothesis,
   but it must remain clearly hypothetical.

   Example:
   GOOD:
   "The move may reflect broader sector conditions not yet
   represented in the supplied evidence."

   BAD:
   "The sector rallied strongly and pushed the stock higher."

7. Do not claim that any supplied source proves causality.

8. The supplied claims are evidence candidates and context.
   They do not automatically explain the anomaly.

9. Prefer hypotheses that would require different evidence
   to confirm or reject.

10. Do not invent numerical observations.

11. Do not output BUY, SELL, LONG, SHORT, or other trading
    recommendations.

The hypothesis text must contain only the candidate
explanation.

Any fact or mechanism that is not explicitly observed
in the supplied anomaly or claims must instead be placed
in assumptions.

Examples:

BAD:
"The revenue beat caused investors to reprice the stock."

GOOD:
text:
"The anomaly may reflect reassessment of the company's
reported financial performance."

assumptions:
- "Reported results differed materially from market expectations."
- "Market participants changed their valuation because of those results."

Do not state an assumption as though it had been observed.



Return JSON only:

{
  "hypotheses": [
    {
      "text": "...",
    }
  ]
}


""".strip()


def generate_hypotheses(
    anomaly: AnomalyEvent,
    claims: tuple[ExtractedClaim, ...],
    provider: StructuredLLM,
    *, financial_context: str = "",
) -> tuple[
    ModelRun,
    tuple[Hypothesis, ...],
]:
    anomaly_json = json.dumps(
        anomaly.model_dump(mode="json"),
        indent=2,
    )

    if claims:
        claim_context = "\n\n".join(
            (
                f"CLAIM {index}\n"
                f"type: {claim.claim_type.value}\n"
                f"text: {claim.text}\n"
                f"source_quote: {claim.source_quote}"
            )
            for index, claim in enumerate(
                claims,
                start=1,
            )
        )
    else:
        claim_context = (
            "No extracted source claims are currently available."
        )

    raw = provider.complete_json(
        system=SYSTEM_PROMPT,
        user=(
            "ANOMALY:\n"
            f"{anomaly_json}\n\n"
            "VALIDATED SOURCE CLAIMS:\n"
            f"{claim_context}\n\nDETERMINISTIC FINANCIAL CONTEXT:\n{financial_context}"
        ),
        reasoning=False,
    )

    parsed = _HypothesisResponse.model_validate(
        raw
    )

    # Remove exact duplicate hypothesis texts while
    # preserving model order.
    unique_texts: list[str] = []
    seen: set[str] = set()

    for candidate in parsed.hypotheses:
        text = candidate.text.strip()

        if not text:
            continue

        key = text.casefold()

        if key in seen:
            continue

        seen.add(key)
        unique_texts.append(text)

    if not 2 <= len(unique_texts) <= 4:
        raise ValueError(
            "Hypothesis generation must produce "
            "between 2 and 4 distinct hypotheses; "
            f"received {len(unique_texts)}."
        )

    created_at = datetime.now(
        timezone.utc
    )

    run_digest = sha1(
        (
            f"{provider.provider_name}|"
            f"{provider.model_name}|"
            f"{anomaly.anomaly_id}|"
            f"{PROMPT_VERSION}|"
            f"{created_at.isoformat()}"
        ).encode("utf-8")
    ).hexdigest()[:12]

    run = ModelRun(
        **getattr(provider, 'last_completion', {}),
        run_id=f"MR-HYP-{run_digest}",
        provider=provider.provider_name,
        model=provider.model_name,
        operation=ModelOperation.HYPOTHESIS_GENERATION,
        prompt_version=PROMPT_VERSION,
        created_at=created_at,
    )

    hypotheses: list[Hypothesis] = []

    for text in unique_texts:
        digest = sha1(
            (
                f"{anomaly.anomaly_id}|"
                f"{text}"
            ).encode("utf-8")
        ).hexdigest()[:12]

        hypotheses.append(
            Hypothesis(
                hypothesis_id=f"H-{digest}",
                text=text,
                assumptions=candidate.assumptions,
                model_run_id=run.run_id,
            )
        )

    return (
        run,
        tuple(hypotheses),
    )
