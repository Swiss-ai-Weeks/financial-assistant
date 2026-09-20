from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha1
import json

from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from financial_assistant.domain import (ArgumentNodeKind, Hypothesis, ModelOperation,
    ModelRun, RelationKind, RelationshipAssessment)
from .provider import StructuredLLM
from .evidence_arguments import select_arguments, log_relationship_diagnostics

PROMPT_VERSION = 'relation-assessment-v2'


class _AssessmentCandidate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    # Accept legacy claim-only provider responses, but always validate typed pairs.
    source_kind: ArgumentNodeKind = ArgumentNodeKind.CLAIM
    source_id: str = Field(validation_alias=AliasChoices('source_id', 'claim_id'))
    hypothesis_id: str
    relation: RelationKind
    strength: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str
    assumptions: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()


class _AssessmentResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    assessments: tuple[_AssessmentCandidate, ...]


SYSTEM_PROMPT = '''Assess typed analytical evidence against the EXACT supplied hypothesis.
The hypothesis is not evidence. Do not invent facts or infer causality just because
items concern the same event. You are not deciding whether the hypothesis is true.

Before choosing a relation, consider whether the evidence increases plausibility,
decreases plausibility, directly conflicts with a required premise, or is merely
nondiscriminating context:
- supports: genuinely increases plausibility of the EXACT hypothesis; does NOT mean
  proves the whole causal story.
- weakens: decreases plausibility without conflicting with a necessary premise.
- contradicts: conflicts with something required by the hypothesis.
- context_for: relevant but does not materially change plausibility.
- unrelated: has no meaningful bearing on this hypothesis.

Do not classify evidence as context_for merely because it fails to prove the full
causal mechanism. If it genuinely makes the EXACT hypothesis more plausible,
classify supports and separately record additional premises in assumptions or
missing_information. Do not require balanced counts or any minimum relation count.

A financial result does NOT automatically support a hypothesis saying that the
market moved because of that result. Investor reaction, expectations and timing
may still be missing. For example a 640bp margin decline versus 120bp for eligible
peers may support 'unusually severe relative margin pressure', but be only context
for 'margin pressure caused stock-price divergence'. Preserve the missing bridge.
Peer behavior alone is analogy/context, not causal proof about the target.

Preserve evidence types: a grounded Claim is a source statement (possibly a forecast
or interpretation); an Observation records a value; a Calculation is deterministic
arithmetic with input lineage; an Inference is model-derived/analytically inferred,
NOT a direct observation. An inference's assumptions and input quality limit its
support. Do not count dependent arguments as independent corroboration. Do not
recompute supplied calculations. Research query intent is execution provenance,
never a rule for assigning a relation.

Preserve source_kind, source_id and hypothesis_id exactly as opaque identities.
Return exactly one assessment per supplied evidence/hypothesis pair. State rationale,
additional premises in assumptions, and missing evidence in missing_information.
Return JSON only: {"assessments": [{"source_kind": "calculation", "source_id": "...",
"hypothesis_id": "...", "relation": "context_for", "strength": null,
"rationale": "...", "assumptions": [], "missing_information": []}]}'''


def _assess_one_hypothesis(arguments, hypothesis, provider):
    raw = provider.complete_json(system=SYSTEM_PROMPT, user=(
        'ANALYTICAL EVIDENCE:\n' + json.dumps([a.context() for a in arguments], default=str) +
        f'\nHYPOTHESIS ID: {hypothesis.hypothesis_id}\nTEXT: {hypothesis.text}\n'
        f'Return exactly {len(arguments)} assessments.'), reasoning=False)
    parsed = _AssessmentResponse.model_validate(raw)
    expected = {(a.source_kind, a.source_id, hypothesis.hypothesis_id) for a in arguments}
    returned = [(a.source_kind, a.source_id, a.hypothesis_id) for a in parsed.assessments]
    if len(returned) != len(set(returned)):
        raise ValueError('Relationship assessment returned duplicate evidence-hypothesis pairs')
    if set(returned) != expected:
        raise ValueError('Relationship assessment pairs do not match the supplied evidence and hypothesis')
    created_at = datetime.now(timezone.utc)
    digest = sha1(f'{provider.provider_name}|{provider.model_name}|{hypothesis.hypothesis_id}|{PROMPT_VERSION}|{created_at.isoformat()}'.encode()).hexdigest()[:12]
    run = ModelRun(run_id=f'MR-REL-{digest}', provider=provider.provider_name, model=provider.model_name,
        operation=ModelOperation.RELATION_ASSESSMENT, prompt_version=PROMPT_VERSION, created_at=created_at)
    assessments = []
    for item in parsed.assessments:
        # Include the execution ID: repeated assessments must remain distinct.
        digest = sha1(f'{run.run_id}|{item.source_kind}|{item.source_id}|{item.hypothesis_id}|{item.relation}'.encode()).hexdigest()[:12]
        assessments.append(RelationshipAssessment(assessment_id=f'RA-{digest}',
            source_kind=item.source_kind, source_id=item.source_id,
            target_kind=ArgumentNodeKind.HYPOTHESIS, target_id=item.hypothesis_id,
            relation=item.relation, strength=item.strength, rationale=item.rationale.strip(),
            assumptions=tuple(s.strip() for s in item.assumptions if s.strip()),
            missing_information=tuple(s.strip() for s in item.missing_information if s.strip()),
            model_run_id=run.run_id))
    return run, tuple(assessments)


def assess_relationships(claims, hypotheses: tuple[Hypothesis, ...], provider: StructuredLLM, *,
                         observations=(), calculations=(), inferences=(), max_workers=1, max_arguments=16):
    """Shared typed assessor; the original three positional arguments remain valid.

    The first collection may also contain native analytical objects/EvidenceArguments.
    Each hypothesis gets a bounded selection and its own execution record.
    """
    items = (*claims, *calculations, *observations, *inferences)
    if not items:
        raise ValueError('At least one evidence argument is required.')
    if not hypotheses:
        raise ValueError('At least one hypothesis is required.')
    if max_workers < 1:
        raise ValueError('max_workers must be at least 1.')
    def assess(hypothesis):
        return _assess_one_hypothesis(select_arguments(items, hypothesis, max_arguments), hypothesis, provider)
    if max_workers == 1 or len(hypotheses) == 1:
        results = [assess(h) for h in hypotheses]
    else:
        with ThreadPoolExecutor(max_workers=min(max_workers, len(hypotheses)), thread_name_prefix='claimgraph-relation') as executor:
            results = list(executor.map(assess, hypotheses))
    runs = tuple(r for r, _ in results)
    assessments = tuple(a for _, batch in results for a in batch)
    log_relationship_diagnostics(assessments)
    return runs, assessments
