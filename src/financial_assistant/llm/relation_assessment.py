from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1

from pydantic import BaseModel, ConfigDict, Field

from financial_assistant.domain import (
    ArgumentNodeKind,
    ExtractedClaim,
    Hypothesis,
    ModelOperation,
    ModelRun,
    RelationKind,
    RelationshipAssessment,
)

from .provider import StructuredLLM


PROMPT_VERSION = "relation-assessment-v1"


class _AssessmentCandidate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    claim_id: str
    hypothesis_id: str

    relation: RelationKind

    strength: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    rationale: str

    assumptions: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()


class _AssessmentResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    assessments: tuple[
        _AssessmentCandidate,
        ...
    ]


SYSTEM_PROMPT = """
Assess the epistemic relationship between validated source
claims and candidate explanatory hypotheses.

You are NOT deciding whether a hypothesis is true.

For every supplied claim-hypothesis pair, classify the
relationship as exactly one of:

- supports
- contradicts
- weakens
- context_for
- unrelated

Definitions:

supports:
The claim provides evidence that makes the hypothesis more
plausible.

contradicts:
The claim directly conflicts with something required by the
hypothesis.

weakens:
The claim counts against the hypothesis but does not directly
contradict it.

context_for:
The claim is relevant background but does not by itself make
the explanatory hypothesis substantially more or less likely.

unrelated:
The claim has no meaningful bearing on the hypothesis.

Important rules:

1. The claim is evidence. The hypothesis is not evidence.

2. Do not infer causality merely because a claim and hypothesis
   concern the same event.

3. A financial result does NOT automatically support a
   hypothesis saying that the market moved because of that
   result.

4. If the missing link is investor reaction, expectations,
   positioning, timing, or another unobserved mechanism,
   normally classify the claim as context_for unless the
   supplied claim directly bears on that mechanism.

5. State any additional premise required for the relationship
   in assumptions.

6. State evidence that would help resolve uncertainty in
   missing_information.

7. Do not invent facts.

8. Preserve claim_id and hypothesis_id exactly.

9. Return exactly one assessment for every supplied
   claim-hypothesis pair.

Return JSON only:

{
  "assessments": [
    {
      "claim_id": "...",
      "hypothesis_id": "...",
      "relation": "context_for",
      "strength": 0.5,
      "rationale": "...",
      "assumptions": [],
      "missing_information": []
    }
  ]
}
""".strip()


def assess_relationships(
    claims: tuple[ExtractedClaim, ...],
    hypotheses: tuple[Hypothesis, ...],
    provider: StructuredLLM,
) -> tuple[
    tuple[ModelRun, ...],
    tuple[RelationshipAssessment, ...],
]:
    """
    Assess claims against hypotheses in small batches.

    One model call is made per hypothesis. This reduces
    omission risk and preserves truthful execution
    provenance: each inference call receives its own
    ModelRun.
    """

    if not claims:
        raise ValueError(
            "At least one claim is required."
        )

    if not hypotheses:
        raise ValueError(
            "At least one hypothesis is required."
        )

    claim_context = "\n\n".join(
        (
            f"CLAIM ID: {claim.claim_id}\n"
            f"TYPE: {claim.claim_type.value}\n"
            f"TEXT: {claim.text}\n"
            f"SOURCE QUOTE: {claim.source_quote}"
        )
        for claim in claims
    )

    runs: list[ModelRun] = []
    assessments: list[RelationshipAssessment] = []

    for hypothesis in hypotheses:
        hypothesis_context = (
            f"HYPOTHESIS ID: {hypothesis.hypothesis_id}\n"
            f"TEXT: {hypothesis.text}"
        )

        raw = provider.complete_json(
            system=SYSTEM_PROMPT,
            user=(
                "VALIDATED CLAIMS:\n"
                f"{claim_context}\n\n"
                "CANDIDATE HYPOTHESIS:\n"
                f"{hypothesis_context}\n\n"
                f"Return exactly {len(claims)} assessments: "
                "one for every supplied claim against this "
                "single hypothesis."
            ),
            reasoning=False,
        )

        parsed = _AssessmentResponse.model_validate(
            raw
        )

        expected_pairs = {
            (
                claim.claim_id,
                hypothesis.hypothesis_id,
            )
            for claim in claims
        }

        returned_pairs = [
            (
                item.claim_id,
                item.hypothesis_id,
            )
            for item in parsed.assessments
        ]

        if len(returned_pairs) != len(
            set(returned_pairs)
        ):
            raise ValueError(
                "Relationship assessment returned "
                "duplicate claim-hypothesis pairs for "
                f"{hypothesis.hypothesis_id}."
            )

        if set(returned_pairs) != expected_pairs:
            missing_pairs = sorted(
                expected_pairs - set(returned_pairs)
            )

            unexpected_pairs = sorted(
                set(returned_pairs) - expected_pairs
            )

            raise ValueError(
                "Relationship assessment pairs do not "
                "match the supplied claims and hypothesis.\n"
                f"Hypothesis: {hypothesis.hypothesis_id}\n"
                f"Expected: {len(expected_pairs)} pairs\n"
                f"Returned: {len(returned_pairs)} pairs\n"
                f"Missing: {missing_pairs}\n"
                f"Unexpected: {unexpected_pairs}"
            )

        created_at = datetime.now(timezone.utc)

        run_digest = sha1(
            (
                f"{provider.provider_name}|"
                f"{provider.model_name}|"
                f"{hypothesis.hypothesis_id}|"
                f"{PROMPT_VERSION}|"
                f"{created_at.isoformat()}"
            ).encode("utf-8")
        ).hexdigest()[:12]

        run = ModelRun(
            run_id=f"MR-REL-{run_digest}",
            provider=provider.provider_name,
            model=provider.model_name,
            operation=ModelOperation.RELATION_ASSESSMENT,
            prompt_version=PROMPT_VERSION,
            created_at=created_at,
        )

        runs.append(run)

        for candidate in parsed.assessments:
            digest = sha1(
                (
                    f"{candidate.claim_id}|"
                    f"{candidate.hypothesis_id}|"
                    f"{candidate.relation.value}"
                ).encode("utf-8")
            ).hexdigest()[:12]

            assessments.append(
                RelationshipAssessment(
                    assessment_id=f"RA-{digest}",
                    source_kind=ArgumentNodeKind.CLAIM,
                    source_id=candidate.claim_id,
                    target_kind=ArgumentNodeKind.HYPOTHESIS,
                    target_id=candidate.hypothesis_id,
                    relation=candidate.relation,
                    strength=candidate.strength,
                    rationale=candidate.rationale.strip(),
                    assumptions=tuple(
                        item.strip()
                        for item in candidate.assumptions
                        if item.strip()
                    ),
                    missing_information=tuple(
                        item.strip()
                        for item in candidate.missing_information
                        if item.strip()
                    ),
                    model_run_id=run.run_id,
                )
            )

    return tuple(runs), tuple(assessments)

