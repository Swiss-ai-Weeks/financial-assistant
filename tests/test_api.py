"""
End-to-end tests of the HTTP API.

Every network dependency is replaced at the repository
boundary: market data, symbol search, news, article
fetching and the language model. Controllers, services
and the ClaimGraph pipeline run for real.
"""

import re
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from financial_assistant.api import dependencies as deps
from financial_assistant.api.main import create_app
from financial_assistant.api.models import Instrument, NewsItem
from financial_assistant.api.repositories import (
    InstrumentRepository,
    InvestigationRepository,
    MarketDataRepository,
    NewsRepository,
    PortfolioRepository,
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


class FakeLLM:
    provider_name = "fake"
    model_name = "fake-model"

    def complete_json(self, *, system, user, reasoning=False):
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
    universe = tmp_path / "universe.txt"
    universe.write_text("BBB\nCCC\n")

    seed = tmp_path / "seed.json"
    seed.write_text(
        '{"name": "Test Book", "positions": '
        '[{"ticker": "AAA", "name": "Bank AAA", "shares": 100}]}'
    )

    market = MarketDataRepository(
        tmp_path / "market",
        history_days=800,
        cache_minutes=60,
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
        as_of=LAST_SESSION.date(),
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
            deps.get_discovery_service: lambda: DiscoveryService(
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
            ),
            deps.get_market_service: lambda: MarketService(market, review_days=30),
            deps.get_anomaly_service: lambda: anomalies,
            deps.get_news_service: lambda: news,
            deps.get_instrument_repository: lambda: instruments,
            deps.get_portfolio_repository: lambda: portfolios,
            deps.get_investigation_service: lambda: investigations,
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

    pairs = {(fit["ticker_a"], fit["ticker_b"]) for fit in scan["fits"]}

    assert ("AAA", "BBB") in pairs
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

    assert body["points"][-1]["z_score"] < -body["entry"]


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


def test_investigation_explains_an_anomaly_from_admissible_news(client):
    anomaly = client.get("/api/anomalies?strategy=pairs").json()[0]

    response = client.post(
        "/api/investigations", json={"anomaly_id": anomaly["anomaly_id"]}
    )

    assert response.status_code == 202

    run = response.json()

    assert run["status"] == "completed", run["error"]
    assert [stage["status"] for stage in run["stages"]] == ["done"] * 7

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

    verdicts = {tick["horizon"]: tick for tick in week["ticks"]}

    assert verdicts["1w"]["unusual"]
    assert not verdicts["1y"]["available"]

    assert client.get("/api/microscope/AAA?horizon=1y").status_code == 400
    assert client.get("/api/microscope/AAA?horizon=2h").status_code == 400
    assert client.get("/api/microscope/ZZZ?horizon=1w").status_code == 404


def test_discovery_funnel_narrows_to_a_setup(client):
    body = client.get("/api/discovery").json()
    counts = [step["count"] for step in body["funnel"]]

    assert body["funnel"][0]["label"] == "securities scanned"
    assert counts[0] == 3 and counts[1] == 3

    # Every stage can only keep or drop candidates.
    assert counts[1:] == sorted(counts[1:], reverse=True)

    for setup in body["setups"]:
        # AAA fell below the relationship: it is the cheap leg.
        assert setup["long"] == "AAA" and setup["short"] in ("BBB", "CCC")
        assert setup["outcome"]["analogues"] >= 5
        assert len(setup["invalidation"]) == 3
