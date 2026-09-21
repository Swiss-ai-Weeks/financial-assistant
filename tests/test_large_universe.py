import json
from datetime import date

import numpy as np
import pandas as pd

from financial_assistant.anomaly_detection.scalable import fit_large_universe
from financial_assistant.api.repositories import InstrumentRepository


def market(seed: int = 7, sessions: int = 320) -> pd.DataFrame:
    """
    Two cointegrated pairs, one per currency group, a European
    calendar with its own holidays, and noise names.
    """

    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end="2026-03-20", periods=sessions)

    def walk():
        return np.cumsum(rng.normal(0, 0.012, sessions))

    us, eu = walk(), walk()

    series = {
        "USA1": 4.0 + us,
        "USA2": 3.5 + 0.9 * us + rng.normal(0, 0.004, sessions),
        "EUR1.DE": 4.2 + eu,
        "EUR2.DE": 3.9 + 1.1 * eu + rng.normal(0, 0.004, sessions),
        # Tracks the US driver, but is quoted in euros.
        "EURX.DE": 3.0 + 0.95 * us + rng.normal(0, 0.004, sessions),
        "NOISE1": 4.0 + walk(),
        "NOISE2": 4.0 + walk(),
    }

    rows = []

    for ticker, log_price in series.items():
        for index, (day, value) in enumerate(zip(days, log_price)):
            # Every 40th European session is a local holiday.
            if ticker.endswith(".DE") and index % 40 == 5:
                continue

            rows.append(
                {"date": day, "ticker": ticker, "close": float(np.exp(value))}
            )

    return pd.DataFrame(rows)


GROUPS = {
    "USA1": "us/USD",
    "USA2": "us/USD",
    "NOISE1": "us/USD",
    "NOISE2": "us/USD",
    "EUR1.DE": "eu/EUR",
    "EUR2.DE": "eu/EUR",
    "EURX.DE": "eu/EUR",
}


def fit(**overrides):
    prices = market()

    return fit_large_universe(
        prices,
        **{
            "start": prices["date"].min(),
            "end": date(2026, 2, 20),
            "corr_min": 0.7,
            "alpha": 0.05,
            "groups": GROUPS,
            "formation_observations": 252,
            **overrides,
        },
    )


def pairs(fits):
    return {frozenset((f.ticker_a, f.ticker_b)) for f in fits}


def test_relationships_are_found_across_different_calendars():
    found = pairs(fit())

    assert frozenset(("USA1", "USA2")) in found
    # Local holidays would have emptied a shared calendar.
    assert frozenset(("EUR1.DE", "EUR2.DE")) in found


def test_a_pair_never_crosses_currencies():
    for pair in pairs(fit()):
        assert len({GROUPS[t] for t in pair}) == 1, pair

    # Without groups the same data does pair USD with EUR.
    crossing = fit(groups=None)

    assert any(
        len({GROUPS[t] for t in pair}) == 2 for pair in pairs(crossing)
    )


def test_focus_only_looks_for_partners_of_the_holding():
    found = pairs(fit(focus=frozenset({"EUR1.DE"})))

    assert found == {frozenset(("EUR1.DE", "EUR2.DE"))}


def test_nothing_after_the_formation_window_is_used():
    for relationship in fit():
        assert relationship.formation_end <= date(2026, 2, 20)
        assert relationship.nobs <= 252


def test_the_catalogue_answers_without_the_network(tmp_path):
    catalog = tmp_path / "securities.json"
    catalog.write_text(
        json.dumps(
            {
                "securities": [
                    {
                        "ticker": "NESN.SW",
                        "name": "NESTLE",
                        "exchange": "SIX",
                        "sector": "Consumer Staples",
                        "currency": "CHF",
                        "universes": ["stoxx_600_proxy"],
                    },
                    {
                        "ticker": "COHU",
                        "name": "COHU",
                        "sector": "Information Technology",
                        "currency": "USD",
                        "universes": ["russell_2500_proxy"],
                    },
                ]
            }
        )
    )

    def offline(query, limit):
        raise OSError("Yahoo is down")

    instruments = InstrumentRepository(
        tmp_path / "missing.txt",
        searcher=offline,
        catalog_file=catalog,
    )

    assert set(instruments.universe) == {"NESN.SW", "COHU"}
    assert instruments.sectors["COHU"] == "Information Technology"
    assert instruments.groups["NESN.SW"] == "stoxx_600_proxy/CHF"

    assert instruments.describe("NESN.SW").name == "NESTLE"
    assert [i.ticker for i in instruments.search("nest")] == ["NESN.SW"]


def test_the_shipped_catalogue_is_the_merged_universe():
    from financial_assistant.api.config import PROJECT_ROOT

    instruments = InstrumentRepository(
        PROJECT_ROOT / "data" / "universes" / "us_large_caps.txt",
        searcher=lambda query, limit: (),
        catalog_file=PROJECT_ROOT / "data" / "universe" / "securities.json",
    )

    assert instruments.catalog_size > 3000
    assert len(instruments.universe) >= instruments.catalog_size
