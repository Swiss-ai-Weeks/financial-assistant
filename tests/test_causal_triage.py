from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from financial_assistant.domain import AnomalyEvent, ModelOperation
from financial_assistant.llm import (
    TriageHeadline,
    TriageVerdict,
    triage_anomaly,
)


CLOSE = datetime(2026, 9, 18, 21, tzinfo=timezone.utc)

ANOMALY = AnomalyEvent(
    anomaly_id="PAIR-GDX-GLD-2026-09-18",
    ticker="GDX",
    related_entities=("GLD",),
    detected_at=CLOSE,
    anomaly_type="cointegration_spread_deviation",
    summary="GDX/GLD spread at z=+3.13",
)


def headline(number, title, *, hours_before=24, summary=""):
    return TriageHeadline(
        headline_id=f"N{number}",
        ticker="GDX",
        title=title,
        summary=summary,
        publisher="Example Wire",
        published_at=CLOSE - timedelta(hours=hours_before),
    )


HEADLINES = (
    headline(1, "Gold miners rally as sector rotation lifts cyclicals"),
    headline(2, "Newmont cuts 2027 production guidance", summary="Costs rise."),
)


class Provider:
    provider_name = "fake"
    model_name = "fake-model"

    def __init__(self, response):
        self.response = response
        self.prompts = []

    def complete_json(self, *, system, user, reasoning=False):
        assert reasoning is False
        self.prompts.append(user)

        return self.response


def test_verdict_rests_on_a_supplied_headline():
    provider = Provider(
        {
            "verdict": "lasting_event",
            "headline_id": "N2",
            "why_now": "  Newmont cut 2027 production\n guidance, weighing on miners. ",
        }
    )

    run, triage = triage_anomaly(ANOMALY, HEADLINES, provider)

    assert triage.verdict == TriageVerdict.LASTING_EVENT
    assert triage.headline_id == "N2"
    assert triage.why_now == (
        "Newmont cut 2027 production guidance, weighing on miners."
    )

    assert run.operation == ModelOperation.CAUSAL_TRIAGE
    assert triage.model_run_id == run.run_id

    # The model saw the headlines and their short handles.
    assert "N1 | GDX" in provider.prompts[0]
    assert "Newmont cuts 2027 production guidance\nCosts rise." in provider.prompts[0]


def test_a_cited_headline_that_was_never_supplied_is_rejected():
    provider = Provider(
        {"verdict": "transient_event", "headline_id": "N9", "why_now": "Made up."}
    )

    with pytest.raises(ValueError, match="not supplied"):
        triage_anomaly(ANOMALY, HEADLINES, provider)


def test_an_event_without_a_citation_is_rejected():
    provider = Provider(
        {"verdict": "lasting_event", "headline_id": None, "why_now": "Trust me."}
    )

    with pytest.raises(ValueError, match="not supplied"):
        triage_anomaly(ANOMALY, HEADLINES, provider)


def test_no_event_never_carries_a_citation():
    provider = Provider(
        {"verdict": "no_event", "headline_id": "N1", "why_now": "Nothing explains it."}
    )

    _, triage = triage_anomaly(ANOMALY, HEADLINES, provider)

    assert triage.verdict == TriageVerdict.NO_EVENT
    assert triage.headline_id is None


def test_unknown_verdicts_are_rejected():
    provider = Provider(
        {"verdict": "buy_the_dip", "headline_id": "N1", "why_now": "x"}
    )

    with pytest.raises(ValidationError):
        triage_anomaly(ANOMALY, HEADLINES, provider)


def test_hindsight_headlines_never_reach_the_model():
    provider = Provider({"verdict": "no_event", "why_now": "x"})
    late = headline(3, "Miners slump the next morning", hours_before=-12)

    with pytest.raises(ValueError, match="after the anomaly"):
        triage_anomaly(ANOMALY, (*HEADLINES, late), provider)

    assert provider.prompts == []


def test_only_the_most_relevant_headlines_are_offered():
    many = tuple(headline(n, f"Story {n}") for n in range(1, 31))
    provider = Provider({"verdict": "transient_event", "headline_id": "N20", "why_now": "x"})

    # N20 exists, but it was beyond the cut and never shown.
    with pytest.raises(ValueError, match="not supplied"):
        triage_anomaly(ANOMALY, many, provider)

    assert "N12 |" in provider.prompts[0]
    assert "N13 |" not in provider.prompts[0]
