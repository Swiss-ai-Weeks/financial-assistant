from datetime import datetime, timezone

import pytest

from financial_assistant.domain import (
    ClaimType,
    ExtractedClaim,
    Hypothesis,
    ModelOperation,
    RelationKind,
)

from financial_assistant.llm import (
    assess_relationships,
)


CLAIMS = (
    ExtractedClaim(
        claim_id="C-1",
        text="Revenue increased 50%.",
        claim_type=ClaimType.REPORTED_FACT,
        document_id="DOC-1",
        source_quote="Revenue increased 50%.",
        model_run_id="MR-CLAIMS",
    ),
    ExtractedClaim(
        claim_id="C-2",
        text="Management expects revenue growth.",
        claim_type=ClaimType.FORECAST,
        document_id="DOC-1",
        source_quote="Management expects revenue growth.",
        model_run_id="MR-CLAIMS",
    ),
)


HYPOTHESES = (
    Hypothesis(
        hypothesis_id="H-1",
        text=(
            "The anomaly may reflect reassessment "
            "of company growth."
        ),
        model_run_id="MR-HYP",
    ),
    Hypothesis(
        hypothesis_id="H-2",
        text=(
            "The anomaly may reflect technical "
            "market conditions."
        ),
        model_run_id="MR-HYP",
    ),
)


class GoodProvider:
    provider_name = "fake"
    model_name = "fake-model"

    def complete_json(
        self,
        *,
        system,
        user,
        reasoning=False,
    ):
        assert reasoning is False

        if "HYPOTHESIS ID: H-1" in user:
            return {
                "assessments": [
                    {
                        "claim_id": "C-1",
                        "hypothesis_id": "H-1",
                        "relation": "context_for",
                        "strength": 0.6,
                        "rationale": (
                            "Revenue growth is relevant to "
                            "growth reassessment, but does not "
                            "show that investors caused the move."
                        ),
                        "assumptions": [],
                        "missing_information": [
                            "What were prior market expectations?"
                        ],
                    },
                    {
                        "claim_id": "C-2",
                        "hypothesis_id": "H-1",
                        "relation": "context_for",
                        "strength": 0.5,
                        "rationale": (
                            "The forecast is relevant context "
                            "but does not establish repricing."
                        ),
                        "assumptions": [],
                        "missing_information": [],
                    },
                ]
            }

        if "HYPOTHESIS ID: H-2" in user:
            return {
                "assessments": [
                    {
                        "claim_id": "C-1",
                        "hypothesis_id": "H-2",
                        "relation": "unrelated",
                        "strength": 0.1,
                        "rationale": (
                            "Revenue does not directly evidence "
                            "technical market conditions."
                        ),
                        "assumptions": [],
                        "missing_information": [],
                    },
                    {
                        "claim_id": "C-2",
                        "hypothesis_id": "H-2",
                        "relation": "unrelated",
                        "strength": 0.1,
                        "rationale": (
                            "The forecast does not evidence "
                            "market structure."
                        ),
                        "assumptions": [],
                        "missing_information": [],
                    },
                ]
            }

        raise AssertionError(
            f"Unexpected hypothesis in provider input:\n{user}"
        )


class MissingPairProvider:
    provider_name = "fake"
    model_name = "fake-model"

    def complete_json(
        self,
        *,
        system,
        user,
        reasoning=False,
    ):
        return {
            "assessments": [
                {
                    "claim_id": "C-1",
                    "hypothesis_id": "H-1",
                    "relation": "context_for",
                    "strength": 0.5,
                    "rationale": "Relevant context.",
                    "assumptions": [],
                    "missing_information": [],
                }
            ]
        }


def test_assesses_every_pair():
    runs, assessments = assess_relationships(
        CLAIMS,
        HYPOTHESES,
        GoodProvider(),
    )


    assert len(runs) == 2

    assert all(
            run.operation == ModelOperation.RELATION_ASSESSMENT for run in runs
            )

    assert len(assessments) == 4

    assert {
        assessment.relation
        for assessment in assessments
    } == {
        RelationKind.CONTEXT_FOR,
        RelationKind.UNRELATED,
    }

    run_ids = {
            run.run_id
            for run in runs
            }

    assert all(
            assessment.model_run_id in run_ids
            for assessment in assessments
            )


def test_missing_pair_is_rejected():
    with pytest.raises(
        ValueError,
        match="do not match",
    ):
        assess_relationships(
            CLAIMS,
            HYPOTHESES,
            MissingPairProvider(),
        )
