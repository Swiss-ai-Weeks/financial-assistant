from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha1
import json

from pydantic import BaseModel, ConfigDict, Field

from financial_assistant.domain import (
    AnomalyEvent,
    ModelOperation,
    ModelRun,
)

from .provider import StructuredLLM, complete_structured


PROMPT_VERSION = "causal-triage-v2"

MAX_HEADLINES = 12
MAX_SUMMARY_CHARS = 300
MAX_WHY_NOW_CHARS = 320


class TriageVerdict(StrEnum):
    """
    What the headlines say about WHY a relationship moved.

    The distinction that matters for a relationship is not
    "news or no news" but whether the cause changes what one
    leg is worth for good:

      lasting_event    guidance, litigation, M&A, regulation,
                       a lost customer. The gap is a repricing
                       and should not be expected to close.

      transient_event  a one-off reaction, a sector rotation,
                       a rating change, positioning. The gap
                       is a dislocation.

      no_event         nothing in the headlines explains it.
                       Also a dislocation, of unknown origin.
    """

    LASTING_EVENT = "lasting_event"
    TRANSIENT_EVENT = "transient_event"
    NO_EVENT = "no_event"


class TriageHeadline(BaseModel):
    """
    One headline offered to the model. `headline_id` is a
    short handle ("N1") because models copy short
    identifiers far more reliably than hashes.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    headline_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1)

    title: str = Field(min_length=1)
    summary: str = ""
    publisher: str | None = None

    published_at: datetime


class CausalTriage(BaseModel):
    """
    A fast first reading of one anomaly. It decides what is
    worth a full investigation; it is not the investigation.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    anomaly_id: str = Field(min_length=1)

    verdict: TriageVerdict

    # The headline the verdict rests on. Always one of the
    # supplied headlines, and absent only for no_event.
    headline_id: str | None = None

    why_now: str = Field(min_length=1)

    model_run_id: str = Field(min_length=1)


class _TriageResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    verdict: TriageVerdict
    headline_id: str | None = None
    why_now: str


SYSTEM_PROMPT = """
Triage a quantitative market anomaly against news headlines.

You are given a statistical anomaly in the relationship
between securities and a numbered list of headlines that were
published BEFORE the anomaly became observable.

Decide which ONE of these best describes the headlines:

- lasting_event: a headline reports a company-specific
  development that durably changes what one security is
  worth (guidance change, earnings surprise with a changed
  outlook, litigation, regulation, M&A, loss or win of a
  major customer, management change, capital action).

- transient_event: a headline reports something that moved
  the price but does not durably change value (analyst rating
  or price-target change, sector rotation, index or flow
  effects, a one-day reaction, general market commentary).

- no_event: no headline explains the anomaly.

Rules:

1. Use ONLY the supplied headlines. Do not use outside
   knowledge of later events.
2. A headline that merely mentions the company is not a cause.
3. Opinion pieces, stock-picking lists and price recaps are
   not lasting events.
4. For lasting_event and transient_event, headline_id MUST be
   the id of the single most relevant supplied headline.
   For no_event, headline_id MUST be null.
5. why_now is ONE sentence, at most 40 words, that a trader
   can read at a glance. State what the headline reports and
   which security it concerns, naming the company. Never
   mention headline ids such as N3, the z-score, or the word
   "cointegration": the reader sees those elsewhere. Do not
   give investment advice and do not predict prices.
6. If you are unsure between lasting_event and
   transient_event, choose transient_event.

Return JSON only:

{
  "verdict": "lasting_event | transient_event | no_event",
  "headline_id": "N3",
  "why_now": "..."
}
""".strip()


def triage_anomaly(
    anomaly: AnomalyEvent,
    headlines: tuple[TriageHeadline, ...],
    provider: StructuredLLM,
) -> tuple[
    ModelRun,
    CausalTriage,
]:
    """
    One model call per anomaly, over headlines and summaries
    only. No article is fetched: this stage exists to be
    cheap enough to run on every candidate.

    The model proposes; this function verifies. A verdict
    that cites a headline which was not supplied, or none
    when one is required, is rejected rather than repaired.
    """

    late = [
        headline.headline_id
        for headline in headlines
        if headline.published_at > anomaly.detected_at
    ]

    if late:
        raise ValueError(
            "Headlines published after the anomaly "
            f"cannot explain it: {late}"
        )

    offered = headlines[:MAX_HEADLINES]

    headline_context = "\n\n".join(
        (
            f"{headline.headline_id} | {headline.ticker} | "
            f"{headline.published_at:%Y-%m-%d %H:%M} UTC | "
            f"{headline.publisher or 'unknown source'}\n"
            f"{headline.title}"
            + (
                f"\n{headline.summary[:MAX_SUMMARY_CHARS]}"
                if headline.summary
                else ""
            )
        )
        for headline in offered
    )

    if not headline_context:
        headline_context = "No headlines were published."

    raw = complete_structured(
        provider,
        system=SYSTEM_PROMPT,
        user=(
            "ANOMALY:\n"
            + json.dumps(
                anomaly.model_dump(mode="json"),
                indent=2,
            )
            + "\n\nHEADLINES:\n"
            + headline_context
        ),
        response_model=_TriageResponse,
        reasoning=False,
    )

    parsed = _TriageResponse.model_validate(raw)

    offered_ids = {
        headline.headline_id
        for headline in offered
    }

    if parsed.verdict == TriageVerdict.NO_EVENT:
        headline_id = None

    elif parsed.headline_id not in offered_ids:
        raise ValueError(
            "Triage cited a headline that was not "
            f"supplied: {parsed.headline_id!r}"
        )

    else:
        headline_id = parsed.headline_id

    why_now = " ".join(parsed.why_now.split())

    if not why_now:
        raise ValueError(
            "Triage returned an empty explanation."
        )

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
        run_id=f"MR-TRIAGE-{run_digest}",
        provider=provider.provider_name,
        model=provider.model_name,
        operation=ModelOperation.CAUSAL_TRIAGE,
        prompt_version=PROMPT_VERSION,
        created_at=created_at,
    )

    return run, CausalTriage(
        anomaly_id=anomaly.anomaly_id,
        verdict=parsed.verdict,
        headline_id=headline_id,
        why_now=why_now[:MAX_WHY_NOW_CHARS],
        model_run_id=run.run_id,
    )
