from datetime import datetime, timezone

import pytest

from financial_assistant.domain import (
    AnomalyEvent,
    ModelOperation,
)

from financial_assistant.llm import (
    generate_hypotheses,
)


ANOMALY = AnomalyEvent(
    anomaly_id="ANOM-TEST",
    ticker="AAA",
    related_entities=("BBB",),
    detected_at=datetime(
        2026,
        9,
        17,
        tzinfo=timezone.utc,
    ),
    anomaly_type="pair_divergence",
    summary=(
        "AAA and BBB diverged unusually relative "
        "to their historical relationship."
    ),
    severity=0.8,
    metadata={
        "z_score": 3.4,
    },
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

        return {
            "hypotheses": [
                {
                    "text": (
                        "The divergence reflects a "
                        "company-specific repricing in AAA."
                    ),
                    "assumptions": [
                        "Market participants changed their valuation of AAA.",
                        ],
                },
                {
                    "text": (
                        "The divergence reflects a "
                        "company-specific repricing in BBB."
                    ),
                    "assumptions": [
                        "Market participants changed their valuation of BBB.",
                        ],
                },
                {
                    "text": (
                        "The move is primarily a temporary "
                        "technical or statistical dislocation."
                    ),
                    "assumptions": [
                        "Market participants changed their valuation.",
                        ],
                },
            ]
        }


class DuplicateProvider:
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
            "hypotheses": [
                {
                    "text": "The anomaly is temporary."
                },
                {
                    "text": "The anomaly is temporary."
                },
            ]
        }


def test_generates_distinct_hypotheses():
    run, hypotheses = generate_hypotheses(
        ANOMALY,
        (),
        GoodProvider(),
    )

    assert len(hypotheses) == 3

    assert (
        run.operation
        == ModelOperation.HYPOTHESIS_GENERATION
    )

    assert all(
        hypothesis.model_run_id == run.run_id
        for hypothesis in hypotheses
    )

    assert len({
        hypothesis.hypothesis_id
        for hypothesis in hypotheses
    }) == 3

    assert isinstance(
    hypotheses[0].assumptions,
    tuple,
    )


def test_duplicate_hypotheses_are_rejected_after_deduplication():
    with pytest.raises(
        ValueError,
        match="between 2 and 4",
    ):
        generate_hypotheses(
            ANOMALY,
            (),
            DuplicateProvider(),
        )
