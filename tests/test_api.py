"""
End-to-end tests of the HTTP API.

Every network dependency is replaced at the repository
boundary: market data, symbol search, news, article
fetching and the language model. Controllers, services
and the ClaimGraph pipeline run for real.
"""

import json
import re
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from financial_assistant.analytics import PairAnalogueBase, PairBreak
from financial_assistant.api import dependencies as deps
from financial_assistant.api.main import create_app
from financial_assistant.api.models import Instrument, NewsItem
from financial_assistant.api.repositories import (
    InstrumentRepository,
    InvestigationRepository,
    MarketDataRepository,
    NewsRepository,
    PortfolioRepository,
    TriageRepository,
)
from financial_assistant.api.services import (
    AnomalyService,
    DiscoveryService,
    InvestigationService,
    MarketService,
    MicroscopeService,
    NewsService,
    PortfolioService,
    PostMortemService,
)
from financial_assistant.domain import SourceDocument


# Long enough for a one-week reading: a year to estimate beta,
# a year to measure volatility, then the horizon itself.
SESSIONS = 560
LAST_SESSION = pd.bdate_range(end="2026-09-18", periods=SESSIONS)[-1]

ARTICLE = (
    "Bank AAA shares fell sharply after the lender warned that "
    "unrealised bond losses had widened to 90 billion dollars. "
    "Analysts said rival BBB was less exposed to long-dated bonds."
)


def fake_download(tickers, *, start, end):
    """
    AAA and BBB share one random walk, so they are
    cointegrated. AAA breaks away, on heavy volume, in
    the final sessions. ZZZ is an unknown symbol.
    """

    days = pd.bdate_range(end=LAST_SESSION, periods=SESSIONS)
    rng = np.random.default_rng(11)

    common = np.cumsum(rng.normal(0, 0.01, SESSIONS))
    frames = []

    for ticker in tickers:
        if ticker == "ZZZ":
            continue

        # Seeded by name: a ticker's history must not depend
        # on which batch it was downloaded in.
        seed = sum(map(ord, ticker))
        noise = np.random.default_rng(seed).normal(0, 0.003, SESSIONS)
        closes = 100 * np.exp(common + noise)
        volumes = np.full(SESSIONS, 1_000_000.0) + rng.normal(0, 20_000, SESSIONS)

        if ticker == "AAA":
            closes[-4:] *= [0.95, 0.93, 0.91, 0.90]
            volumes[-4] = 5_000_000

        frames.append(
            pd.DataFrame(
                {
                    "date": days,
                    "ticker": ticker,
                    "open": closes,
                    "high": closes * 1.004,
                    "low": closes * 0.996,
                    "close": closes,
                    "volume": volumes,
                }
            )
        )

    if not frames:
        # The real downloader answers an unknown symbol
        # with an empty frame, not an error.
        columns = ["date", "ticker", "open", "high", "low", "close", "volume"]

        return pd.DataFrame(columns=columns), None

    return pd.concat(frames, ignore_index=True), None


def fake_analogue_base(prices, **settings):
    """
    Past breaks that all converged, six at every size, so
    that whatever the fixture's z-score turns out to be it
    has comparable analogues. Replaying years of history
    belongs to test_analytics.
    """

    return PairAnalogueBase(
        universe_size=int(prices["ticker"].nunique()),
        first_as_of=date(2025, 1, 2),
        last_as_of=date(2026, 8, 3),
        breaks=tuple(
            PairBreak(
                as_of=date(2025, month, 3),
                ticker_a="AAA",
                ticker_b="BBB",
                z_score=-float(size),
                return_5_pct=0.8,
                return_10_pct=1.5,
                reverted=True,
            )
            for size in range(2, 60)
            for month in range(1, 7)
        ),
    )


class FakeNewsSource:
    name = "fake-wire"
    local = False

    def fetch(self, ticker, company, *, start=None, end=None):
        close = datetime.combine(
            LAST_SESSION.date(), datetime.min.time(), tzinfo=timezone.utc
        ) + timedelta(hours=21)

        def item(suffix, title, published_at):
            return NewsItem(
                news_id=f"NEWS-{ticker}-{suffix}",
                ticker=ticker,
                title=title,
                url=f"https://news.example.com/{ticker}/{suffix}",
                publisher="Example Wire",
                published_at=published_at,
                summary=ARTICLE,
                provider=self.name,
            )

        return (
            item("before", f"{ticker} warns on bond losses", close - timedelta(days=3)),
            item("after", f"{ticker} rebounds", close + timedelta(days=1)),
        )


class FakeFetcher:
    name = "fake-fetcher"

    def fetch(self, hit, *, retrieved_at):
        return SourceDocument(
            document_id=f"DOC-{hit.hit_id}",
            title=hit.title,
            publisher=hit.publisher,
            url=str(hit.url),
            published_at=hit.published_at,
            retrieved_at=retrieved_at,
            text=ARTICLE,
            lineage_id=f"LIN-{hit.hit_id}",
        )


# What the fake model and its endpoint do in the triage tests.
TRIAGE = {"online": True, "answer": None, "calls": 0}


class FakeLLM:
    provider_name = "fake"
    model_name = "fake-model"

    def complete_json(self, *, system, user, reasoning=False):
        if system.lstrip().startswith("Triage a quantitative"):
            TRIAGE["calls"] += 1

            if TRIAGE["answer"] is not None:
                return TRIAGE["answer"]

            # CCC's break is read as a lasting event, BBB's as noise.
            return {
                "verdict": "lasting_event" if '"CCC"' in user else "transient_event",
                "headline_id": "N1",
                "why_now": "AAA warned that unrealised bond losses widened.",
            }

        if system.lstrip().startswith("Extract atomic"):
            return {
                "claims": [
                    {
                        "text": "AAA warned that unrealised bond losses widened.",
                        "claim_type": "reported_fact",
                        "source_quote": (
                            "unrealised bond losses had widened "
                            "to 90 billion dollars"
                        ),
                    }
                ]
            }

        if system.lstrip().startswith("Decide whether an open evidence"):
            supplied = json.loads(user)["evidence"]

            return {
                "status": "partially_answered" if supplied else "unresolved",
                "summary": "The new article bears on BBB's bond book.",
                "supporting_item_ids": [item["id"] for item in supplied[:1]],
                "contradicting_item_ids": [],
                "remaining_question": "How large is BBB's exposure?",
            }

        if system.lstrip().startswith("Generate competing"):
            return {
                "hypotheses": [
                    {"text": "AAA repriced on its own bond-loss disclosure."},
                    {"text": "A sector-wide rate shock hit both banks."},
                ]
            }

        hypothesis_ids = list(dict.fromkeys(re.findall(r"H-[0-9a-f]+", user)))

        if system.lstrip().startswith("Audit candidate"):
            return {
                "audits": [
                    {
                        "hypothesis_id": hypothesis_id,
                        "assumptions": ["Investors read the disclosure."],
                        "missing_information": ["BBB bond exposure."],
                    }
                    for hypothesis_id in hypothesis_ids
                ]
            }

        return {
            "assessments": [
                {
                    "claim_id": claim_id,
                    "hypothesis_id": hypothesis_ids[0],
                    # One request is made per hypothesis.
                    "relation": (
                        "supports"
                        if "own bond-loss" in user
                        else "context_for"
                    ),
                    "strength": 0.8,
                    "rationale": "The disclosure is company specific.",
                }
                for claim_id in dict.fromkeys(re.findall(r"C-[0-9a-f]+", user))
            ]
        }


@pytest.fixture()
def client(tmp_path):
    TRIAGE.update(online=True, answer=None, calls=0)

    universe = tmp_path / "universe.txt"
    universe.write_text("AAA\nBBB\nCCC\n")

    seed = tmp_path / "seed.json"
    seed.write_text(
        '{"name": "Test Book", "positions": '
        '[{"ticker": "AAA", "name": "Bank AAA", "shares": 100}]}'
    )

    from financial_assistant.api.clock import DeskClock
    from financial_assistant.copilot import CopilotService
    from financial_assistant.llm.model_registry import (
        ModelHealth,
        ModelRegistry,
        ModelSpec,
    )

    # One clock, shared by everything that could leak the future.
    clock = DeskClock(LAST_SESSION.date())

    market = MarketDataRepository(
        tmp_path / "market",
        history_days=800,
        cache_minutes=60,
        as_of=clock,
        downloader=fake_download,
    )

    instruments = InstrumentRepository(
        universe,
        searcher=lambda query, limit: (
            Instrument(ticker="BBB", name="Bank BBB", kind="EQUITY"),
        ),
    )

    portfolios = PortfolioRepository(tmp_path / "portfolio.json", seed_file=seed)

    news = NewsService(
        NewsRepository(tmp_path / "news", (FakeNewsSource(),), cache_minutes=60),
        portfolios,
        instruments,
        review_days=30,
        as_of=clock,
    )

    anomalies = AnomalyService(
        portfolios,
        market,
        instruments,
        review_days=30,
        benchmark="SPY",
        formation_observations=252,
        corr_min=0.5,
        alpha=0.05,
        entry=2.0,
    )

    investigation_store = InvestigationRepository(tmp_path / "investigations")

    investigations = InvestigationService(
        investigation_store,
        anomalies,
        news,
        llm_factory=FakeLLM,
        llm_base_url="http://llm.invalid/v1",
        llm_api_key=None,
        model="fake-model",
        provider="fake",
        document_fetcher=FakeFetcher(),
        run_inline=True,
    )

    discovery = DiscoveryService(
    anomalies,
    news,
    market,
    portfolios,
    instruments,
    cache_dir=tmp_path / "analogues",
    formation_observations=252,
    corr_min=0.5,
    alpha=0.05,
    entry=2.0,
    min_liquidity_musd=1.0,
    analogue_builder=fake_analogue_base,
    triage_store=TriageRepository(tmp_path / "triage"),
    llm_factory=FakeLLM,
    llm_available=lambda: TRIAGE["online"],
)

    app = create_app()

    app.dependency_overrides.update(
        {
            deps.get_postmortem_service: lambda: PostMortemService(
                anomalies,
                portfolios,
                market,
                investigation_store,
                review_days=30,
                benchmark="SPY",
            ),
            deps.get_microscope_service: lambda: MicroscopeService(
                market, portfolios, instruments, anomalies, benchmark="SPY"
            ),
            # One instance: a scan's state lives on the service.
            deps.get_discovery_service: lambda: discovery,
            deps.get_market_service: lambda: MarketService(market, review_days=30),
            deps.get_anomaly_service: lambda: anomalies,
            deps.get_news_service: lambda: news,
            deps.get_instrument_repository: lambda: instruments,
            deps.get_portfolio_repository: lambda: portfolios,
            deps.get_investigation_service: lambda: investigations,
            deps.get_clock: lambda: clock,
            # Never the configured endpoint: tests do not leave
            # the machine.
            deps.get_copilot_service: lambda: CopilotService(
                ModelRegistry(
                    (
                        ModelSpec(
                            id="default",
                            provider="fake",
                            model="fake-model",
                            base_url="http://llm.invalid/v1",
                        ),
                    ),
                    factories={"default": FakeLLM},
                    prober=lambda spec, key: ModelHealth(online=True),
                )
            ),
            deps.get_portfolio_service: lambda: PortfolioService(
                portfolios,
                instruments,
                market,
                anomalies,
                benchmark="SPY",
                review_days=30,
            ),
        }
    )

    return TestClient(app)


def test_portfolio_reports_return_against_the_benchmark(client):
    body = client.get("/api/portfolio").json()

    assert body["name"] == "Test Book"
    assert body["benchmark"] == "SPY"
    assert body["window"]["end"] == LAST_SESSION.date().isoformat()

    assert body["active_return_pct"] == pytest.approx(
        body["month_return_pct"] - body["benchmark_return_pct"]
    )

    position = body["positions"][0]

    assert position["ticker"] == "AAA"
    assert position["weight_pct"] == pytest.approx(100.0)
    assert position["month_return_pct"] < -5
    assert position["anomaly_count"] > 0


def test_adding_a_ticker_triggers_a_pair_scan(client):
    response = client.post(
        "/api/portfolio/positions", json={"ticker": "bbb", "shares": 50}
    )

    assert response.status_code == 201

    body = response.json()

    assert [p["ticker"] for p in body["portfolio"]["positions"]] == ["AAA", "BBB"]
    assert body["portfolio"]["positions"][1]["name"] == "Bank BBB"

    scan = body["pair_scan"]

    assert scan["focus"] == ["BBB"]
    assert scan["formation_end"] < scan["monitoring_start"]

    pairs = {frozenset((fit["ticker_a"], fit["ticker_b"])) for fit in scan["fits"]}

    assert {"AAA", "BBB"} in pairs
    assert any(a["strategy"] == "pairs" for a in scan["anomalies"])


def test_portfolio_rejects_duplicates_and_unknown_symbols(client):
    duplicate = client.post("/api/portfolio/positions", json={"ticker": "AAA"})
    unknown = client.post("/api/portfolio/positions", json={"ticker": "ZZZ"})

    assert duplicate.status_code == 409
    assert unknown.status_code == 404
    assert len(client.get("/api/portfolio").json()["positions"]) == 1


def test_removing_a_position(client):
    assert client.delete("/api/portfolio/positions/AAA").json()["positions"] == []
    assert client.delete("/api/portfolio/positions/AAA").status_code == 404


def test_candles_carry_strategy_overlays(client):
    body = client.get("/api/market/AAA/candles?days=60").json()
    last = body["candles"][-1]

    assert (body["fast"], body["slow"]) == (7, 25)
    assert last["time"] == LAST_SESSION.date().isoformat()
    assert all(last[key] is not None for key in ("ma_fast", "ma_slow", "vwap", "twap"))


def test_anomaly_blotter_covers_every_strategy_monitor(client):
    anomalies = client.get("/api/anomalies").json()
    strategies = {a["strategy"] for a in anomalies}

    assert {"vwap", "twap", "pairs"} <= strategies
    assert all(0 <= a["severity"] <= 1 for a in anomalies)

    only_pairs = client.get("/api/anomalies?strategy=pairs").json()

    assert only_pairs
    assert all(a["strategy"] == "pairs" for a in only_pairs)

    cards = client.get("/api/strategies").json()

    assert [card["key"] for card in cards] == ["vwap", "twap", "trend", "pairs"]
    assert sum(card["anomaly_count"] for card in cards) == len(anomalies)


def test_pair_spread_series(client):
    body = client.get("/api/pairs/AAA/BBB/spread").json()
    latest = body["points"][-1]["z_score"]

    assert {body["ticker_a"], body["ticker_b"]} == {"AAA", "BBB"}
    assert abs(latest) > body["entry"]

    # AAA fell. The sign says so from whichever leg is dependent.
    assert (latest < 0) == (body["ticker_a"] == "AAA")


def test_anomaly_news_is_split_at_the_evidence_cutoff(client):
    anomaly = client.get("/api/anomalies?strategy=pairs").json()[0]
    body = client.get(f"/api/news/anomaly/{anomaly['anomaly_id']}").json()

    assert {item["title"] for item in body["admissible"]} == {
        "AAA warns on bond losses",
        "BBB warns on bond losses",
    }

    assert all(item["published_at"] > body["cutoff"] for item in body["hindsight"])
    assert all(item["published_at"] <= body["cutoff"] for item in body["admissible"])


def test_stories_naming_the_company_outrank_passing_mentions():
    from financial_assistant.api.relevance import company_aliases, relevance

    aliases = company_aliases("BAC", "Bank of America Corporation")

    assert "Bank of America" in aliases
    assert "Bank" not in aliases
    assert "Bank of" not in aliases
    assert "Goldman Sachs" in company_aliases("GS", "The Goldman Sachs Group, Inc.")
    assert "NVIDIA" in company_aliases("NVDA", "NVIDIA Corporation")

    def story(title, summary=""):
        return NewsItem(
            news_id=title,
            ticker="BAC",
            title=title,
            url="https://news.example.com/x",
            published_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
            summary=summary,
            provider="fake",
        )

    assert relevance(story("Bank of America slips on bond losses"), aliases) == 2
    assert relevance(story("Banks fall", "Shares of BAC led the drop."), aliases) == 1
    assert relevance(story("NetApp sees strong demand, BofA says"), aliases) == 0
    assert relevance(story("BACK to school sales"), aliases) == 0
    assert relevance(story("Insider sells Bank of Montreal stock"), aliases) == 0


def test_one_story_from_two_providers_is_one_piece_of_evidence():
    from financial_assistant.api.relevance import one_per_story

    def story(url, provider, summary="", title="Lam Research Climbs 5%"):
        return NewsItem(
            news_id=url,
            ticker="LRCX",
            title=title,
            url=url,
            published_at=datetime(2026, 9, 18, 16, 59, tzinfo=timezone.utc),
            summary=summary,
            provider=provider,
        )

    kept = one_per_story(
        [
            story("https://finnhub.io/api/news?id=1", "finnhub", "A long summary."),
            story("https://247wallst.com/lam", "yahoo-finance", "Short."),
            story("https://benzinga.com/x", "finnhub", title="A different story"),
        ]
    )

    assert len(kept) == 2

    # The copy that links the publisher wins over the redirect.
    assert kept[0].url == "https://247wallst.com/lam"


def test_investigation_explains_an_anomaly_from_admissible_news(client):
    anomaly = client.get("/api/anomalies?strategy=pairs").json()[0]

    response = client.post(
        "/api/investigations", json={"anomaly_id": anomaly["anomaly_id"]}
    )

    assert response.status_code == 202

    run = response.json()

    assert run["status"] == "completed", run["error"]
    # news, documents, fundamentals, claims, hypotheses, audit,
    # relations, graph.
    assert [stage["status"] for stage in run["stages"]] == ["done"] * 8

    # Only the two pre-cutoff articles may become evidence.
    assert run["documents_considered"] == 2
    assert run["documents_used"] == 2

    best, other = run["hypotheses"]

    assert best["supporting"] == 1 and best["score"] > other["score"]
    assert best["missing_information"] == ["BBB bond exposure."]

    assert run["claims"][0]["source_quote"] in ARTICLE
    assert run["claims"][0]["url"].startswith("https://news.example.com/")

    kinds = {node["kind"] for node in run["graph"]["nodes"]}

    assert {"anomaly", "hypothesis", "claim", "document"} <= kinds

    stored = client.get(f"/api/investigations/{run['investigation_id']}").json()

    assert stored["status"] == "completed"
    assert client.get("/api/investigations").json()[0]["investigation_id"] == (
        run["investigation_id"]
    )


def test_consent_walls_are_not_mistaken_for_articles():
    from financial_assistant.api.services.investigation_service import (
        matches_headline,
    )

    headline = "Bank of America Slips as Bond Losses Threaten $90 Billion"

    consent = (
        "Si vous ne souhaitez pas que nos partenaires utilisent des "
        "cookies, cliquez sur Refuser tout."
    )

    assert matches_headline("Bond losses at the bank widened. " + ARTICLE, headline)
    assert not matches_headline(consent, headline)


def test_investigation_of_unknown_anomaly_is_not_found(client):
    response = client.post("/api/investigations", json={"anomaly_id": "NOPE"})

    assert response.status_code == 404


# -----------------------------------------------------
# The three stories
# -----------------------------------------------------


def test_postmortem_prices_the_relationship_that_broke(client):
    body = client.get("/api/postmortem").json()

    # AAA broke away from both of its cointegrated partners.
    finding = next(
        f
        for f in body["findings"]
        if f["headline"] == "AAA / BBB — unusual divergence"
    )

    assert finding["statement"].startswith("AAA underperformed BBB by ")

    # 100 shares of a ~$100 stock that fell ~10% after the signal.
    assert -1500 < finding["impact"] < -300

    # Only AAA is held, so a hedge with BBB is priced. Whether
    # it would have helped depends on what BBB did, and the
    # desk reports that honestly either way.
    assert finding["hedged_impact"] is not None
    assert finding["hedged_impact"] != finding["impact"]

    assert finding["relationship"]["pvalue"] < 0.05
    assert finding["signal_date"] <= finding["anomaly"]["observed_on"]
    assert "hedge with BBB" in finding["missed_signal"]

    # Nothing has been investigated yet, and it says so.
    assert finding["explanation"] is None and finding["confidence"] is None

    # Overlapping findings on one holding are not double counted.
    assert body["total_impact"] >= sum(
        f["impact"] for f in body["findings"]
    )


def test_postmortem_carries_the_explanation_once_investigated(client):
    anomaly = client.get("/api/anomalies?strategy=pairs").json()[0]
    client.post("/api/investigations", json={"anomaly_id": anomaly["anomaly_id"]})

    finding = next(
        f
        for f in client.get("/api/postmortem").json()["findings"]
        if f["anomaly"]["anomaly_id"] == anomaly["anomaly_id"]
    )

    assert finding["explanation"] == "AAA repriced on its own bond-loss disclosure."
    assert finding["confidence"] == "medium"
    assert finding["investigation_id"].startswith("INV-")


def test_microscope_reads_the_same_security_differently_per_horizon(client):
    week = client.get("/api/microscope/AAA?horizon=1w").json()

    assert week["reading"]["unusual"]
    assert week["reading"]["abnormal_return_pct"] < -5
    assert "unusual at this horizon" in week["statements"][0]

    # The sector peer did not take part in AAA's break.
    assert any("BBB has not followed" in line for line in week["statements"])
    assert {peer["ticker"] for peer in week["peers"]} == {"BBB", "CCC"}
    assert not any(peer["followed"] for peer in week["peers"])

    # The same reading, for the stock and each peer, at every horizon.
    subject, *others = week["matrix"]

    assert subject["ticker"] == "AAA" and subject["is_subject"]
    assert subject["ticks"] == week["ticks"]
    assert {row["ticker"] for row in others} == {"BBB", "CCC"}
    assert all(len(row["ticks"]) == 5 and row["correlation"] > 0 for row in others)

    # AAA broke alone: its week is unusual, its peers' is not.
    week_of = lambda row: next(t for t in row["ticks"] if t["horizon"] == "1w")

    assert week_of(subject)["unusual"]
    assert not any(week_of(row)["unusual"] for row in others)

    verdicts = {tick["horizon"]: tick for tick in week["ticks"]}

    assert verdicts["1w"]["unusual"]
    assert not verdicts["1y"]["available"]

    assert client.get("/api/microscope/AAA?horizon=1y").status_code == 400
    assert client.get("/api/microscope/AAA?horizon=2h").status_code == 400
    assert client.get("/api/microscope/ZZZ?horizon=1w").status_code == 404


def test_discovery_funnel_narrows_to_a_setup(client):
    body = discover(client)
    counts = [step["count"] for step in body["funnel"]]

    assert body["funnel"][0]["label"] == "securities scanned"
    assert counts[0] == 3 and counts[1] == 3

    # Every stage can only keep or drop candidates.
    assert counts[1:] == sorted(counts[1:], reverse=True)

    # AAA is held, so its broken relationships are the
    # post-mortem's news, not today's discovery.
    assert body["setups"] == []
    assert body["funnel"][-1] == {"label": "new to you", "count": 0, "detail": None}
    assert body["on_your_desk"]

    for setup in body["on_your_desk"]:
        # AAA fell below the relationship: it is the cheap leg.
        assert setup["long"] == "AAA" and setup["short"] in ("BBB", "CCC")
        assert setup["outcome"]["analogues"] >= 5
        assert len(setup["invalidation"]) == 3


def test_discovery_is_about_what_is_not_already_held(client):
    """
    The same break is a discovery for someone who holds
    neither leg, and old news for someone who holds one.
    """

    # Every candidate reads as a dislocation, so this test is
    # only about who holds what.
    TRIAGE["answer"] = {
        "verdict": "transient_event",
        "headline_id": "N1",
        "why_now": "A one-day reaction.",
    }

    client.delete("/api/portfolio/positions/AAA")
    client.post("/api/portfolio/positions", json={"ticker": "CCC"})

    body = discover(client)

    new = {(s["long"], s["short"]) for s in body["setups"]}
    known = {(s["long"], s["short"]) for s in body["on_your_desk"]}

    assert ("AAA", "BBB") in new
    assert ("AAA", "CCC") in known
    assert not new & known


def test_analogue_record_is_reused_only_while_current_and_never_from_the_future():
    def record(last_as_of):
        return PairAnalogueBase(
            universe_size=3,
            first_as_of=date(2025, 1, 2),
            last_as_of=last_as_of,
            breaks=(),
        )

    latest = date(2026, 9, 18)
    is_current = DiscoveryService._is_current

    assert is_current(record(date(2026, 8, 21)), latest)

    # Weeks of recent breaks are missing.
    assert not is_current(record(date(2026, 6, 1)), latest)

    # Built for a later date: on a replayed desk its most
    # recent breaks have not happened yet.
    assert not is_current(record(date(2026, 9, 15)), latest)
    assert not is_current(record(date(2026, 12, 1)), latest)
    assert not is_current(record(None), latest)


def test_sector_prior_admits_related_names_at_a_looser_correlation():
    """
    AAA and BBB correlate about 0.85. Under a 0.95 bar they
    are only tested when they are declared same-sector.
    """

    from financial_assistant.anomaly_detection import fit_pairs

    prices, _ = fake_download(("AAA", "BBB"), start=None, end=None)
    window = {
        "start": prices["date"].iloc[0].date(),
        "end": prices["date"].iloc[300].date(),
        "corr_min": 0.95,
        "alpha": 0.05,
    }

    assert fit_pairs(prices, **window) == ()

    related = fit_pairs(
        prices,
        **window,
        sectors={"AAA": "Banks", "BBB": "Banks"},
        corr_min_same_sector=0.5,
    )

    assert len(related) == 1

    unrelated = fit_pairs(
        prices,
        **window,
        sectors={"AAA": "Banks", "BBB": "Airlines"},
        corr_min_same_sector=0.5,
    )

    assert unrelated == ()


# -----------------------------------------------------
# Causal triage inside discovery
# -----------------------------------------------------


def discover(client):
    """Start a scan and poll until it settles, as the page does."""

    import time

    assert client.post("/api/discovery").status_code == 202

    for _ in range(400):
        job = client.get("/api/discovery").json()

        if job["status"] != "running":
            break

        time.sleep(0.02)

    assert job["status"] == "completed", job["error"]

    return job["discovery"]


def step(body, label):
    return next(s for s in body["funnel"] if s["label"] == label)


def test_nemotron_drops_justified_repricings_in_the_open(client):
    body = discover(client)

    dropped = {frozenset((s["long"], s["short"])) for s in body["repriced"]}
    kept = {frozenset((s["long"], s["short"])) for s in body["on_your_desk"]}

    assert dropped == {frozenset(("AAA", "CCC"))}
    assert kept == {frozenset(("AAA", "BBB"))}

    stage = step(body, "dislocation, not a justified repricing")

    assert stage["count"] == step(body, "liquid enough")["count"] - 1
    assert stage["detail"] == (
        "The model read 2: 1 lasting event dropped, 1 transient, 0 unexplained."
    )

    triage = body["on_your_desk"][0]["triage"]

    assert triage["verdict"] == "transient_event"
    assert triage["model"] == "fake-model"

    # The citation resolves to a real, admissible headline.
    assert triage["headline"]["title"].endswith("warns on bond losses")
    assert triage["headline"]["published_at"] <= "2026-09-18T21:00:00Z"


def test_triage_is_replayed_from_disk_without_a_model(client):
    first = discover(client)
    calls = TRIAGE["calls"]

    assert calls == 2

    TRIAGE["online"] = False
    again = discover(client)

    assert TRIAGE["calls"] == calls
    assert again["repriced"] == first["repriced"]
    assert again["on_your_desk"][0]["triage"] == first["on_your_desk"][0]["triage"]


def test_an_offline_model_drops_nothing(client):
    TRIAGE["online"] = False

    body = discover(client)
    stage = step(body, "dislocation, not a justified repricing")

    assert body["repriced"] == []
    assert stage["count"] == step(body, "liquid enough")["count"]
    assert "offline" in stage["detail"]
    assert all(s["triage"] is None for s in body["on_your_desk"])


def test_an_unverifiable_answer_is_not_a_verdict(client):
    # Cites a headline that was never offered.
    TRIAGE["answer"] = {
        "verdict": "lasting_event",
        "headline_id": "N99",
        "why_now": "Invented.",
    }

    body = discover(client)
    stage = step(body, "dislocation, not a justified repricing")

    assert body["repriced"] == []
    assert "rejected by verification" in stage["detail"]
    assert all(s["triage"] is None for s in body["on_your_desk"])


def test_a_hosted_endpoint_without_a_key_is_not_reported_online(tmp_path):
    """
    Hosted gateways list their models to anyone. Reachable is
    not usable: without a key every real request is a 401.
    """

    from financial_assistant.api.config import Settings

    service = InvestigationService(
        InvestigationRepository(tmp_path),
        anomalies=None,
        news=None,
        llm_factory=FakeLLM,
        llm_base_url="https://integrate.api.nvidia.com/v1",
        llm_api_key=None,
        llm_is_local=False,
        model="nvidia/nemotron-3.5-lightning-30b-a3b",
        provider="nvidia-nim",
        document_fetcher=FakeFetcher(),
    )

    status = service.llm_status()

    assert not status.online
    assert "LLM_API_KEY" in status.detail

    def settings(url):
        return Settings.from_env().__class__(
            **{**Settings.from_env().__dict__, "llm_base_url": url}
        )

    assert settings("http://127.0.0.1:8000/v1").llm_is_local
    assert settings("http://localhost:8000/v1").llm_is_local
    assert settings("http://gpu-box:8000/v1").llm_is_local
    assert settings("http://10.0.3.7:8000/v1").llm_is_local
    assert not settings("https://integrate.api.nvidia.com/v1").llm_is_local


def test_one_word_selects_a_consistent_llm_profile(monkeypatch):
    from financial_assistant.api.config import Settings

    for name in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_WORKERS"):
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setenv("LLM_PROFILE", "hosted")
    hosted = Settings.from_env()

    assert hosted.llm_provider_name == "nvidia-nim"
    assert hosted.llm_model == "nvidia/nemotron-3.5-lightning-30b-a3b"
    assert hosted.llm_workers == 3
    # Long enough for a full-length answer at the measured speed.
    assert hosted.llm_timeout_seconds == 180
    assert not hosted.llm_is_local

    monkeypatch.setenv("LLM_PROFILE", "local")
    local = Settings.from_env()

    assert local.llm_provider_name == "vllm-local"
    assert local.llm_model.endswith("-BF16")
    assert local.llm_is_local
    assert local.llm_workers == 8 and local.llm_timeout_seconds == 120

    # An explicit value still wins over its profile default.
    monkeypatch.setenv("LLM_BASE_URL", "http://10.0.0.5:8000/v1")

    assert Settings.from_env().llm_base_url == "http://10.0.0.5:8000/v1"

    monkeypatch.setenv("LLM_PROFILE", "cloud")

    with pytest.raises(ValueError, match="LLM_PROFILE"):
        Settings.from_env()


def test_runs_orphaned_by_a_restart_do_not_block_the_anomaly(tmp_path):
    from financial_assistant.api.models import (
        Anomaly,
        Investigation,
        InvestigationStage,
        InvestigationStatus,
        StageStatus,
    )

    store = InvestigationRepository(tmp_path)

    store.save(
        Investigation(
            investigation_id="INV-ORPHAN",
            anomaly=Anomaly(
                anomaly_id="A-1",
                ticker="AAA",
                strategy="pairs",
                kind="cointegration_spread_deviation",
                observed_on=date(2026, 9, 18),
                z_score=-3.0,
                threshold=2.0,
                severity=0.5,
                direction="a_below_equilibrium",
                summary="AAA/BBB spread",
            ),
            status=InvestigationStatus.RUNNING,
            created_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
            evidence_cutoff=datetime(2026, 9, 18, 21, tzinfo=timezone.utc),
            model="m",
            provider="p",
            stages=[
                InvestigationStage(key="news", label="News", status=StageStatus.DONE),
                InvestigationStage(key="claims", label="Claims", status=StageStatus.RUNNING),
                InvestigationStage(key="graph", label="Graph"),
            ],
        )
    )

    # A new process comes up with that run still on disk.
    InvestigationService(
        InvestigationRepository(tmp_path),
        anomalies=None,
        news=None,
        llm_factory=FakeLLM,
        llm_base_url="http://llm.invalid/v1",
        llm_api_key=None,
        model="m",
        provider="p",
        document_fetcher=FakeFetcher(),
    )

    run = InvestigationRepository(tmp_path).get("INV-ORPHAN")

    assert run.status == InvestigationStatus.FAILED
    assert "Interrupted" in run.error
    assert [s.status for s in run.stages] == [
        StageStatus.DONE,
        StageStatus.SKIPPED,
        StageStatus.SKIPPED,
    ]


def test_discovery_runs_in_the_background_and_reports_progress(client):
    """
    A first scan replays years of history and takes minutes,
    longer than any proxy keeps a request open. Starting it
    must return at once.
    """

    assert client.get("/api/discovery").json()["status"] == "idle"

    started = client.post("/api/discovery")

    assert started.status_code == 202
    assert started.json()["status"] in ("running", "completed")
    assert started.json()["discovery"] is None or started.json()["status"] == "completed"

    body = discover(client)
    job = client.get("/api/discovery").json()

    assert job["status"] == "completed" and job["stage"] == "Done"
    assert job["seconds"] is not None
    assert job["discovery"]["funnel"] == body["funnel"]


def test_a_divergence_is_read_around_its_onset_and_peak_not_only_today():
    """
    Found on real data: AVGO/NVDA broke on Aug 19 and was
    detected on Sep 18. Ordered by recency, all twelve
    articles an investigation read were from Sep 18 and none
    of the 230 published around the onset, which included the
    actual cause.
    """

    from financial_assistant.api.models import Anomaly
    from financial_assistant.api.services.news_service import NewsService

    anomaly = Anomaly(
        anomaly_id="PAIR-AVGO-NVDA-2026-09-18",
        ticker="AVGO",
        related_tickers=("NVDA",),
        strategy="pairs",
        kind="cointegration_spread_deviation",
        observed_on=date(2026, 9, 18),
        z_score=-2.8,
        threshold=2.0,
        severity=0.5,
        direction="a_below_equilibrium",
        summary="AVGO/NVDA spread",
        metrics={"first_flag": "2026-08-19", "peak_date": "2026-09-04"},
    )

    keys = NewsService.key_dates(anomaly)

    assert [(k.label, k.day.isoformat()) for k in keys] == [
        ("onset", "2026-08-19"),
        ("peak", "2026-09-04"),
        ("latest", "2026-09-18"),
    ]

    def story(day, hour, name, relevance):
        item = NewsItem(
            news_id=name,
            ticker="AVGO",
            title=name,
            url=f"https://news.example.com/{name}",
            published_at=datetime(2026, *day, hour, tzinfo=timezone.utc),
            provider="fake",
        )

        return item, relevance

    stories = [
        story((9, 18), 15, "today-a", 2),
        story((9, 18), 12, "today-b", 2),
        story((9, 17), 12, "yesterday", 2),
        story((9, 4), 14, "peak", 2),
        story((8, 19), 16, "onset-names-company", 2),
        story((8, 19), 20, "onset-passing-mention", 0),
        story((8, 18), 9, "day-before-onset", 2),
        # The day AFTER the onset cannot have caused it.
        story((8, 20), 9, "after-onset", 2),
        story((8, 30), 9, "in-between", 2),
    ]

    ordered = NewsService._by_key_date(
        [item for item, _ in stories],
        {item.news_id: relevance for item, relevance in stories},
        keys,
    )

    names = [item.news_id for item in ordered]

    # The dates take turns, so the first three span all of them.
    assert names[:3] == ["onset-names-company", "peak", "today-a"]

    # Around a date: naming the company beats a passing mention,
    # then the closest to that session's close.
    assert names.index("onset-names-company") < names.index("day-before-onset")
    assert names.index("day-before-onset") < names.index("onset-passing-mention")

    # Nothing is lost, and what is near no key date comes last.
    assert sorted(names) == sorted(item.news_id for item, _ in stories)
    assert set(names[-2:]) == {"after-onset", "in-between"}


def test_a_single_session_signal_has_one_key_date():
    from financial_assistant.api.models import Anomaly
    from financial_assistant.api.services.news_service import NewsService

    spike = Anomaly(
        anomaly_id="VOLUME_SPIKE-CVX-2026-09-18",
        ticker="CVX",
        strategy="vwap",
        kind="volume_spike",
        observed_on=date(2026, 9, 18),
        z_score=9.0,
        threshold=3.0,
        severity=1.0,
        direction="down",
        summary="CVX volume spike",
    )

    assert [(k.label, k.day) for k in NewsService.key_dates(spike)] == [
        ("latest", date(2026, 9, 18))
    ]

    # Onset and peak on the same session are one date, not two.
    same_day = spike.model_copy(
        update={"metrics": {"first_flag": "2026-09-18", "peak_date": "2026-09-18"}}
    )

    assert [k.label for k in NewsService.key_dates(same_day)] == [
        "onset / peak / latest"
    ]


# -----------------------------------------------------
# Models, follow-ups, time travel, portfolio workspace
# -----------------------------------------------------


def test_the_same_anomaly_can_be_explained_by_each_configured_model(client):
    models = client.get("/api/investigations/models").json()

    assert models["default_id"] == "default"
    assert [m["id"] for m in models["models"]] == ["default"]
    # Never a URL or a key: the list is drawn in the browser.
    assert "base_url" not in models["models"][0]

    anomaly = client.get("/api/anomalies?strategy=pairs").json()[0]

    run = client.post(
        "/api/investigations",
        json={"anomaly_id": anomaly["anomaly_id"], "model_id": "default"},
    ).json()

    assert run["model_id"] == "default"
    assert run["usage"]["calls"] > 0

    unknown = client.post(
        "/api/investigations",
        json={"anomaly_id": anomaly["anomaly_id"], "model_id": "gpt-99"},
    )

    assert unknown.status_code == 404


def test_a_follow_up_researches_one_open_question_once(client):
    anomaly = client.get("/api/anomalies?strategy=pairs").json()[0]

    run = client.post(
        "/api/investigations", json={"anomaly_id": anomaly["anomaly_id"]}
    ).json()

    gap = next(
        node
        for node in run["graph"]["nodes"]
        if node["kind"] in ("missing_evidence", "evidence_requirement")
    )

    response = client.post(
        f"/api/investigations/{run['investigation_id']}/followups",
        json={"requirement_id": gap["node_id"]},
    )

    assert response.status_code == 202

    after = response.json()
    followup = after["followups"][0]

    assert followup["status"] == "completed", followup["error"]
    assert followup["question"] == gap["label"]
    assert [stage["status"] for stage in followup["stages"]] == ["done"] * 7

    # The cycle is recorded in the graph as execution, apart
    # from the evidence, and the question keeps its history.
    kinds = {node["kind"] for node in after["graph"]["nodes"]}

    assert {"agent_action", "research_task", "tool_call"} <= kinds
    assert after["graph"]["followups"][0]["requirement_id"] == gap["node_id"]

    resolved = next(
        n for n in after["graph"]["nodes"] if n["node_id"] == gap["node_id"]
    )

    assert resolved["data"]["followup_history"]

    # Something that is not an open question cannot be researched.
    claim = next(n for n in run["graph"]["nodes"] if n["kind"] == "claim")

    refused = client.post(
        f"/api/investigations/{run['investigation_id']}/followups",
        json={"requirement_id": claim["node_id"]},
    )

    assert refused.status_code == 404


def test_the_desk_travels_in_time_without_a_restart(client):
    live = client.get("/api/market/AAA/candles?days=30").json()["candles"]
    past = live[-10]["time"]

    moved = client.put("/api/system/as-of", json={"as_of": past})

    assert moved.status_code == 200
    assert moved.json()["as_of"] == past

    replayed = client.get("/api/market/AAA/candles?days=30").json()["candles"]

    # Later sessions no longer exist for anything on the desk.
    assert replayed[-1]["time"] == past

    assert client.put("/api/system/as-of", json={"as_of": "2999-01-01"}).status_code == 400

    client.put("/api/system/as-of", json={"as_of": None})

    assert (
        client.get("/api/market/AAA/candles?days=30").json()["candles"][-1]["time"]
        == live[-1]["time"]
    )


def test_the_book_can_be_stated_as_weights_and_analysed(client):
    rejected = client.put(
        "/api/portfolio/weights",
        json={"positions": [{"ticker": "AAA", "weight": 0.5}]},
    )

    assert rejected.status_code == 400

    book = client.put(
        "/api/portfolio/weights",
        json={
            "name": "Two banks",
            "notional": 1_000_000,
            "positions": [
                {"ticker": "AAA", "weight": 0.6},
                {"ticker": "BBB", "weight": 0.4},
            ],
        },
    ).json()

    assert book["name"] == "Two banks"
    assert round(book["market_value"]) == 1_000_000

    weights = {p["ticker"]: round(p["weight_pct"]) for p in book["positions"]}

    assert weights == {"AAA": 60, "BBB": 40}

    analysis = client.get("/api/portfolio/analysis").json()

    assert analysis["status"] == "available", analysis
    assert analysis["return_20"]["formula_version"]
    assert set(analysis["securities"]) == {"AAA", "BBB"}
    # Provenance is hashed and counted, not shipped.
    assert "inputs" not in analysis["provenance"]
    assert analysis["provenance"]["input_sha256"]

    simulation = client.post(
        "/api/portfolio/simulate",
        json={"ticker_a": "AAA", "ticker_b": "CCC", "gross_overlay": 0.02},
    ).json()

    assert simulation["status"] == "available", simulation
    assert "NOT an expected return forecast" in simulation["interpretation"]


def test_copilot_may_move_the_view_but_never_the_graph(client):
    context = {
        "nodes": [{"id": "hypothesis:H-1", "kind": "hypothesis", "label": "A"}],
        "graph_summary": {"counts": {"hypothesis": 1}},
    }

    # The shared fake answers with assessments, which is not a
    # Copilot reply: it is refused, not passed on.
    response = client.post(
        "/api/copilot",
        json={"question": "What am I looking at?", "context": context},
    )

    assert response.status_code == 400

    too_long = client.post(
        "/api/copilot",
        json={"question": "x" * 2001, "context": context},
    )

    assert too_long.status_code == 400
