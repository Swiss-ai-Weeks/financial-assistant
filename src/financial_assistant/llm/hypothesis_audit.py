from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
import json

from pydantic import BaseModel, ConfigDict

from financial_assistant.domain import (
    AnomalyEvent,
    ExtractedClaim,
    Hypothesis,
    HypothesisAudit,
    ModelOperation,
    ModelRun,
)

from .provider import StructuredLLM


PROMPT_VERSION = "hypothesis-audit-v3-fundamentals"


class _AuditCandidate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    hypothesis_id: str
    assumptions: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()


class _AuditResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    audits: tuple[_AuditCandidate, ...]


SYSTEM_PROMPT = """
Audit candidate hypotheses for hidden or unsupported premises.

You are NOT generating new hypotheses.

The anomaly and validated source claims are the only
observations that may be treated as known.

For each supplied hypothesis:

1. Identify propositions that would need to be true for
   the hypothesis to be justified but are not explicitly
   observed in the supplied anomaly or claims.

2. Put those propositions in assumptions.

3. Put concrete evidence questions or information gaps
   in missing_information.

4. Do not treat the hypothesis itself as evidence.

5. Do not invent observations.

6. Do not convert uncertainty into fact.

7. Keep assumptions specific to that hypothesis.
   Do not copy generic assumptions across hypotheses
   unless they genuinely apply to each one.

IDENTIFIER RULES

- hypothesis_id is an opaque identifier supplied by the application.
- Copy hypothesis_id EXACTLY from HYPOTHESES TO AUDIT.
- Do not create, shorten, normalize, renumber, translate, or otherwise alter IDs.
- Return exactly one audit for every supplied hypothesis.
- Return no audit for any hypothesis not supplied.
- Use each supplied hypothesis_id exactly once.

Example:

Hypothesis:
"The anomaly may reflect reassessment of reported
financial performance."

Possible assumptions:
- "Reported results differed materially from prior
   market expectations."
- "Market participants changed their valuation after
   receiving the new information."

Possible missing_information:
- "What were consensus expectations before the results?"
- "How did the security trade immediately before and
   after the announcement?"

Return JSON only:

{
  "audits": [
    {
      "hypothesis_id": "...",
      "assumptions": [
        "..."
      ],
      "missing_information": [
        "..."
      ]
    }
  ]
}
""".strip()


def _clean_unique(
    values: tuple[str, ...],
) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        cleaned = value.strip()

        if not cleaned:
            continue

        key = cleaned.casefold()

        if key in seen:
            continue

        seen.add(key)
        result.append(cleaned)

    return tuple(result)


def _validate_audit_ids(
    parsed: _AuditResponse,
    hypotheses: tuple[Hypothesis, ...],
) -> None:
    expected_ids = {
        hypothesis.hypothesis_id
        for hypothesis in hypotheses
    }

    returned_ids = [
        audit.hypothesis_id
        for audit in parsed.audits
    ]

    if len(returned_ids) != len(set(returned_ids)):
        raise ValueError(
            "Hypothesis audit returned duplicate hypothesis IDs."
        )

    if set(returned_ids) != expected_ids:
        raise ValueError(
            "Hypothesis audit IDs do not match the supplied "
            "hypotheses."
        )


def audit_hypotheses(
    anomaly: AnomalyEvent,
    claims: tuple[ExtractedClaim, ...],
    hypotheses: tuple[Hypothesis, ...],
    provider: StructuredLLM,
    *, financial_context: str = "",
) -> tuple[
    ModelRun,
    tuple[HypothesisAudit, ...],
]:
    if not hypotheses:
        raise ValueError(
            "At least one hypothesis is required for audit."
        )

    anomaly_json = json.dumps(
        anomaly.model_dump(mode="json"),
        indent=2,
    )

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

    if not claim_context:
        claim_context = "No validated source claims available."

    hypothesis_context = "\n\n".join(
        (
            f"HYPOTHESIS ID: {hypothesis.hypothesis_id}\n"
            f"TEXT: {hypothesis.text}"
        )
        for hypothesis in hypotheses
    )

    raw = provider.complete_json(
        system=SYSTEM_PROMPT,
        user=(
            "ANOMALY:\n"
            f"{anomaly_json}\n\n"
            "VALIDATED SOURCE CLAIMS:\n"
            f"{claim_context}\n\nDETERMINISTIC FINANCIAL CONTEXT:\n{financial_context}\n\n"
            "HYPOTHESES TO AUDIT:\n"
            f"{hypothesis_context}"
        ),
        reasoning=False,
    )

    parsed = _AuditResponse.model_validate(raw)

    try:
        _validate_audit_ids(parsed, hypotheses)
    except ValueError:
        repaired = provider.complete_json(
            system=SYSTEM_PROMPT,
            user=(
                "Your previous response used invalid hypothesis identifiers.\n\n"
                "Allowed hypothesis IDs (exact JSON strings):\n"
                f"{json.dumps([h.hypothesis_id for h in hypotheses])}\n\n"
                "HYPOTHESES TO AUDIT:\n"
                f"{hypothesis_context}\n\n"
                "ANOMALY:\n"
                f"{anomaly_json}\n\n"
                "VALIDATED SOURCE CLAIMS:\n"
                f"{claim_context}\n\nDETERMINISTIC FINANCIAL CONTEXT:\n{financial_context}\n\n"
                "Return the audits again. Use each allowed ID exactly once.\n"
                "Do not create, shorten, normalize, renumber, translate or modify any ID.\n"
                "Preserve the audit content where possible. "
                "Never assign IDs by list position or guess an ambiguous identity.\n\n"
                "Previous response:\n"
                f"{json.dumps(raw, indent=2)}"
            ),
            reasoning=False,
        )
        parsed = _AuditResponse.model_validate(repaired)
        _validate_audit_ids(parsed, hypotheses)

    created_at = datetime.now(timezone.utc)

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
        run_id=f"MR-HYP-AUDIT-{run_digest}",
        provider=provider.provider_name,
        model=provider.model_name,
        operation=ModelOperation.HYPOTHESIS_AUDIT,
        prompt_version=PROMPT_VERSION,
        created_at=created_at,
    )

    audits: list[HypothesisAudit] = []

    for candidate in parsed.audits:
        assumptions = _clean_unique(
            candidate.assumptions
        )

        missing_information = _clean_unique(
            candidate.missing_information
        )

        digest = sha1(
            (
                candidate.hypothesis_id
                + "|"
                + "|".join(assumptions)
                + "|"
                + "|".join(missing_information)
            ).encode("utf-8")
        ).hexdigest()[:12]

        audits.append(
            HypothesisAudit(
                audit_id=f"HA-{digest}",
                hypothesis_id=candidate.hypothesis_id,
                assumptions=assumptions,
                missing_information=missing_information,
                model_run_id=run.run_id,
            )
        )

    return run, tuple(audits)
