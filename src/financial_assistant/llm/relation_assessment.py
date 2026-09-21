from __future__ import annotations

from concurrent.futures import (
    ThreadPoolExecutor,
)
from datetime import datetime, timezone
from hashlib import sha1

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from financial_assistant.domain import (
    ArgumentNodeKind,
    ExtractedClaim,
    Hypothesis,
    ModelOperation,
    ModelRun,
    RelationKind,
    RelationshipAssessment,
)

from .evidence_arguments import (
    EvidenceArgument,
    evidence_argument,
    select_arguments,
)
from .provider import (
    StructuredLLM,
    complete_structured,
    completion_metadata,
)


PROMPT_VERSION = "relation-assessment-v5-typed"

# Claims judged per request. Asked for twelve assessments in
# one answer, the real model returned one and the whole
# investigation failed; asked for four, it returns four.
# Short answers also finish sooner and run in parallel.
BATCH_SIZE = 4

NO_RATIONALE = "The model gave no rationale for this classification."


class _AssessmentCandidate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    # Identifies the evidence judged. The wire name predates
    # typed evidence: it may be a claim, an observation, a
    # calculation or an inference, and `source_id` is accepted
    # as a synonym.
    claim_id: str = Field(
        validation_alias=AliasChoices("claim_id", "source_id"),
    )
    hypothesis_id: str

    relation: RelationKind

    strength: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )

    # Plain JSON mode does not enforce required fields, and
    # the first real run dropped this one on every answer.
    # The relation and its strength carry the verdict, so a
    # missing explanation is recorded as missing, not fatal.
    rationale: str = ""

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

Evidence may also be typed, and its kind limits what it can
show:
- claim: a statement grounded in a quoted source. It may be a
  forecast or an interpretation, not a fact.
- observation: a recorded value, such as a figure from an SEC
  filing.
- calculation: deterministic arithmetic over observations,
  computed by the application. Never recompute it.
- inference: derived by a model. NOT a direct observation; its
  assumptions limit what it can support.
Wherever these rules say "claim" they mean any such item.

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

8. Preserve claim_id and hypothesis_id exactly. claim_id is
   the CLAIM ID or EVIDENCE ID of the item, whatever its kind.

9. Return exactly one assessment for every supplied
   claim-hypothesis pair.

10. A company's financial figures describe the company. They
    are context for "the price moved because of X" unless the
    evidence also bears on investor reaction, expectations or
    timing. Behaviour of peers is analogy, never causal proof.

11. Do not classify evidence as context_for merely because it
    fails to prove the whole causal story: if it makes the
    EXACT hypothesis more plausible it supports, and the
    missing premises go in assumptions.

12. rationale is REQUIRED in every assessment: one sentence,
    at most 30 words, saying why this relation was chosen.
    Never omit it and never leave it empty.

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


def _assess_one_hypothesis(
    *,
    claims: tuple[EvidenceArgument, ...],
    hypothesis: Hypothesis,
    provider: StructuredLLM,
) -> tuple[
    ModelRun,
    tuple[RelationshipAssessment, ...],
]:
    """
    Perform one independent relationship-assessment call.

    `claims` is one batch of typed evidence. Keeping the unit aligned to one
    request preserves execution provenance: one inference
    request produces one ModelRun.
    """

    claim_context = "\n\n".join(
        _describe(claim)
        for claim in claims
    )

    kinds = {
        claim.source_id: claim.source_kind
        for claim in claims
    }

    # The decoder is told how many assessments the answer
    # must hold, not only what each one looks like.
    schema = _AssessmentResponse.model_json_schema()

    schema["properties"]["assessments"].update(
        minItems=len(claims),
        maxItems=len(claims),
    )

    # Nor can it misspell an identifier. Models do not copy
    # twelve-character hashes reliably (the first real run
    # returned "H-bba4733" for "H-bba479d15d1c"), so the only
    # ids the decoder may produce are the ones supplied.
    candidate = schema["$defs"]["_AssessmentCandidate"]["properties"]

    candidate["claim_id"] = {
        "type": "string",
        "enum": [claim.source_id for claim in claims],
    }

    candidate["hypothesis_id"] = {
        "type": "string",
        "enum": [hypothesis.hypothesis_id],
    }

    hypothesis_context = (
        f"HYPOTHESIS ID: {hypothesis.hypothesis_id}\n"
        f"TEXT: {hypothesis.text}"
    )

    raw = complete_structured(
        provider,
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
        response_model=_AssessmentResponse,
        schema=schema,
        reasoning=False,
    )

    parsed = _AssessmentResponse.model_validate(
        raw
    )

    # This request was about one hypothesis, so which one is
    # not the model's to say. It matters for providers that
    # cannot constrain decoding; claim ids are still checked.
    parsed = parsed.model_copy(
        update={
            "assessments": tuple(
                candidate.model_copy(
                    update={
                        "hypothesis_id":
                            hypothesis.hypothesis_id,
                    }
                )
                for candidate in parsed.assessments
            )
        }
    )

    expected_pairs = {
        (
            claim.source_id,
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

    created_at = datetime.now(
        timezone.utc
    )

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
        **completion_metadata(provider),
        run_id=f"MR-REL-{run_digest}",
        provider=provider.provider_name,
        model=provider.model_name,
        operation=(
            ModelOperation
            .RELATION_ASSESSMENT
        ),
        prompt_version=PROMPT_VERSION,
        created_at=created_at,
    )

    assessments: list[
        RelationshipAssessment
    ] = []

    for candidate in parsed.assessments:
        # The execution id is part of the identity: the same
        # pair judged again, by another model or in a follow-up,
        # is a different assessment.
        digest = sha1(
            (
                f"{run.run_id}|"
                f"{candidate.claim_id}|"
                f"{candidate.hypothesis_id}|"
                f"{candidate.relation.value}"
            ).encode("utf-8")
        ).hexdigest()[:12]

        assessments.append(
            RelationshipAssessment(
                assessment_id=(
                    f"RA-{digest}"
                ),

                source_kind=kinds[
                    candidate.claim_id
                ],
                source_id=(
                    candidate.claim_id
                ),

                target_kind=(
                    ArgumentNodeKind
                    .HYPOTHESIS
                ),
                target_id=(
                    candidate.hypothesis_id
                ),

                relation=(
                    candidate.relation
                ),

                strength=(
                    candidate.strength
                ),

                rationale=(
                    candidate
                    .rationale
                    .strip()
                    or NO_RATIONALE
                ),

                assumptions=tuple(
                    item.strip()
                    for item
                    in candidate.assumptions
                    if item.strip()
                ),

                missing_information=tuple(
                    item.strip()
                    for item
                    in (
                        candidate
                        .missing_information
                    )
                    if item.strip()
                ),

                model_run_id=run.run_id,
            )
        )

    return (
        run,
        tuple(assessments),
    )


def _describe(argument: EvidenceArgument) -> str:
    """
    One item as the model reads it. Claims keep the layout the
    stage has always used; other kinds say what they are and
    where their value came from.
    """

    summary = argument.provenance_summary

    if argument.source_kind == ArgumentNodeKind.CLAIM:
        return (
            f"CLAIM ID: {argument.source_id}\n"
            f"TYPE: {summary.get('claim_type')}\n"
            f"TEXT: {argument.text}\n"
            f"SOURCE QUOTE: {summary.get('source_quote')}"
        )

    provenance = "; ".join(
        f"{key}={value}"
        for key, value in summary.items()
        if value not in (None, "", (), [])
        and key not in ("input_observation_ids", "input_calculation_ids")
    )

    return (
        f"EVIDENCE ID: {argument.source_id}\n"
        f"KIND: {argument.source_kind.value}\n"
        f"TEXT: {argument.text}\n"
        f"PROVENANCE: {provenance}"
    )


def assess_relationships(
    claims: tuple[ExtractedClaim, ...],
    hypotheses: tuple[Hypothesis, ...],
    provider: StructuredLLM,
    *,
    observations: tuple = (),
    calculations: tuple = (),
    inferences: tuple = (),
    max_workers: int = 1,
    max_arguments: int = 16,
) -> tuple[
    tuple[ModelRun, ...],
    tuple[RelationshipAssessment, ...],
]:
    """
    Assess claims against hypotheses in small batches.

    One model call is made per hypothesis. Calls may run
    concurrently, but every call still receives its own
    ModelRun.

    ThreadPoolExecutor.map preserves input order, so the
    returned runs and assessments remain deterministic with
    respect to hypothesis ordering even if requests finish in
    a different order.
    """

    items = (
        *claims,
        *calculations,
        *observations,
        *inferences,
    )

    if not items:
        raise ValueError(
            "At least one claim is required."
        )

    if not hypotheses:
        raise ValueError(
            "At least one hypothesis is required."
        )

    if max_workers < 1:
        raise ValueError(
            "max_workers must be at least 1."
        )

    # One task per (hypothesis, batch of claims), in a fixed
    # order, so that results are deterministic however the
    # requests happen to finish.
    #
    # SEC filings produce far more figures than an article
    # produces claims. Each hypothesis is therefore judged
    # against a bounded selection (see select_arguments), so
    # the volume of one kind cannot crowd out the others.
    # Claims alone, the historical case, are all kept.
    typed = bool(calculations or observations or inferences)

    tasks = []

    for hypothesis in hypotheses:
        selected = (
            select_arguments(items, hypothesis, limit=max_arguments)
            if typed
            else tuple(evidence_argument(item) for item in items)
        )

        tasks.extend(
            (
                hypothesis,
                selected[start:start + BATCH_SIZE],
            )
            for start in range(
                0,
                len(selected),
                BATCH_SIZE,
            )
        )

    def assess(task):
        hypothesis, batch = task

        return _assess_one_hypothesis(
            claims=batch,
            hypothesis=hypothesis,
            provider=provider,
        )

    if (
        max_workers == 1
        or len(tasks) == 1
    ):
        results = [
            assess(task)
            for task in tasks
        ]

    else:
        with ThreadPoolExecutor(
            max_workers=min(
                max_workers,
                len(tasks),
            ),
            thread_name_prefix=(
                "claimgraph-relation"
            ),
        ) as executor:
            # executor.map intentionally preserves the
            # ordering of tasks.
            results = list(
                executor.map(
                    assess,
                    tasks,
                )
            )

    runs: list[ModelRun] = []
    assessments: list[
        RelationshipAssessment
    ] = []

    for run, batch in results:
        runs.append(run)
        assessments.extend(batch)

    return (
        tuple(runs),
        tuple(assessments),
    )
