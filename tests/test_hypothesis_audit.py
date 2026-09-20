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


class SequenceProvider:
    provider_name = "fake"
    model_name = "fake-model"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def complete_json(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


def response(ids):
    return {"audits": [
        {"hypothesis_id": id_, "assumptions": [f"Premise for {id_}"]}
        for id_ in ids
    ]}


def test_exact_ids_pass_without_retry_and_keep_content():
    provider = SequenceProvider([response(["H-2", "H-1"])])
    run, audits = audit_hypotheses(ANOMALY, (), HYPOTHESES, provider)
    assert len(provider.calls) == 1
    assert [(a.hypothesis_id, a.assumptions) for a in audits] == [
        ("H-2", ("Premise for H-2",)), ("H-1", ("Premise for H-1",)),
    ]
    assert (run.provider, run.model, run.prompt_version) == (
        "fake", "fake-model", "hypothesis-audit-v2",
    )
    assert run.created_at.tzinfo is not None


@pytest.mark.parametrize("ids", [["H-1", "H-1"], ["H-1", "h-2"], ["H-1"]])
def test_invalid_ids_get_one_repair_with_original_context(ids):
    import json

    previous = response(ids)
    provider = SequenceProvider([previous, response(["H-2", "H-1"])])
    run, audits = audit_hypotheses(ANOMALY, (), HYPOTHESES, provider)
    assert len(provider.calls) == 2
    repair = provider.calls[1]
    assert repair["reasoning"] is False
    assert repair["system"] == provider.calls[0]["system"]
    assert json.dumps(previous, indent=2) in repair["user"]
    assert '["H-1", "H-2"]' in repair["user"]
    assert "Use each allowed ID exactly once" in repair["user"]
    assert all(h.text in repair["user"] for h in HYPOTHESES)
    # Reversed model order is retained; no positional reassignment to input IDs.
    assert [(a.hypothesis_id, a.assumptions) for a in audits] == [
        ("H-2", ("Premise for H-2",)), ("H-1", ("Premise for H-1",)),
    ]
    assert all(a.model_run_id == run.run_id for a in audits)


@pytest.mark.parametrize("ids, message", [
    (["H-1", "H-1"], "duplicate hypothesis IDs"),
    (["H-1", "H-02"], "do not match"),
])
def test_failed_repair_is_not_reassigned_or_retried(ids, message):
    provider = SequenceProvider([response(["wrong"]), response(ids)])
    with pytest.raises(ValueError, match=message):
        audit_hypotheses(ANOMALY, (), HYPOTHESES, provider)
    assert len(provider.calls) == 2


@pytest.mark.parametrize("repair", [False, True])
def test_schema_errors_are_not_repaired(repair):
    responses = ([response(["wrong"])] if repair else []) + [
        {"audits": [{"hypothesis_id": "H-1", "unexpected": True}]},
    ]
    provider = SequenceProvider(responses)
    with pytest.raises(ValueError, match="extra_forbidden"):
        audit_hypotheses(ANOMALY, (), HYPOTHESES, provider)
    assert len(provider.calls) == (2 if repair else 1)
