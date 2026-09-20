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


def test_a_single_hypothesis_is_corrected_once_then_accepted():
    """
    Seen on the first real run: with thinking off, the model
    committed to one explanation. Told what was wrong, it
    produces alternatives.
    """

    from datetime import datetime, timezone

    from financial_assistant.domain import AnomalyEvent
    from financial_assistant.llm import generate_hypotheses

    class Provider:
        provider_name = "fake"
        model_name = "fake-model"

        def __init__(self):
            self.prompts = []

        def complete_json(self, *, system, user, reasoning=False):
            self.prompts.append(user)

            if len(self.prompts) == 1:
                return {"hypotheses": [{"text": "The move may reflect X."}]}

            return {
                "hypotheses": [
                    {"text": "The move may reflect X."},
                    {"text": "One possibility is Y."},
                    {"text": "The move could reflect Z."},
                    {"text": "It may be explained by W."},
                    {"text": "A fifth one, beyond the limit."},
                ]
            }

    provider = Provider()

    anomaly = AnomalyEvent(
        anomaly_id="A-1",
        ticker="AAA",
        detected_at=datetime(2026, 9, 18, 21, tzinfo=timezone.utc),
        anomaly_type="volume_spike",
        summary="AAA traded 4x its average volume",
    )

    _, hypotheses = generate_hypotheses(anomaly, (), provider)

    assert len(provider.prompts) == 2
    assert "PREVIOUS ANSWER WAS REJECTED" in provider.prompts[1]
    assert "contained 1 distinct" in provider.prompts[1]

    # More than four is trimmed, not failed.
    assert len(hypotheses) == 4
