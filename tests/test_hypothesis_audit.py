from datetime import datetime, timezone

import pytest

from financial_assistant.domain import (
    AnomalyEvent,
    Hypothesis,
    ModelOperation,
)

from financial_assistant.llm import (
    audit_hypotheses,
)


ANOMALY = AnomalyEvent(
    anomaly_id="ANOM-AUDIT",
    ticker="AAA",
    detected_at=datetime(
        2026,
        9,
        17,
        tzinfo=timezone.utc,
    ),
    anomaly_type="attention_event",
    summary="AAA moved unusually.",
)


HYPOTHESES = (
    Hypothesis(
        hypothesis_id="H-1",
        text=(
            "The anomaly may reflect reassessment "
            "of company fundamentals."
        ),
        model_run_id="MR-GEN",
    ),
    Hypothesis(
        hypothesis_id="H-2",
        text=(
            "The anomaly may reflect technical "
            "market conditions."
        ),
        model_run_id="MR-GEN",
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

        return {
            "audits": [
                {
                    "hypothesis_id": "H-1",
                    "assumptions": [
                        (
                            "Market participants changed "
                            "their valuation."
                        )
                    ],
                    "missing_information": [
                        (
                            "What expectations existed "
                            "before the event?"
                        )
                    ],
                },
                {
                    "hypothesis_id": "H-2",
                    "assumptions": [
                        (
                            "Technical market conditions "
                            "changed materially."
                        )
                    ],
                    "missing_information": [
                        (
                            "What were liquidity and "
                            "trading conditions?"
                        )
                    ],
                },
            ]
        }


class MissingHypothesisProvider:
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
            "audits": [
                {
                    "hypothesis_id": "H-1",
                    "assumptions": [],
                    "missing_information": [],
                }
            ]
        }


def test_audits_every_hypothesis():
    run, audits = audit_hypotheses(
        ANOMALY,
        (),
        HYPOTHESES,
        GoodProvider(),
    )

    assert (
        run.operation
        == ModelOperation.HYPOTHESIS_AUDIT
    )

    assert len(audits) == 2

    assert {
        audit.hypothesis_id
        for audit in audits
    } == {
        "H-1",
        "H-2",
    }

    assert all(
        audit.model_run_id == run.run_id
        for audit in audits
    )


def test_missing_hypothesis_audit_is_rejected():
    with pytest.raises(
        ValueError,
        match="do not match",
    ):
        audit_hypotheses(
            ANOMALY,
            (),
            HYPOTHESES,
            MissingHypothesisProvider(),
        )
