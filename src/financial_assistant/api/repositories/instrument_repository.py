from __future__ import annotations

import json
from pathlib import Path

import yfinance as yf

from financial_assistant.api.models import Instrument


TRADABLE_KINDS = {"EQUITY", "ETF"}


SECTOR_SEPARATOR = "·"


def read_universe(path: Path) -> dict[str, str | None]:
    """
    Tickers of a universe file, each with its sector.

    A header such as "# Energy · majors / E&P" puts the
    tickers below it in the Energy sector. Plain comments
    and files without such headers leave the sector unknown.
    """

    if not path.is_file():
        return {}

    sector: str | None = None
    universe: dict[str, str | None] = {}

    for raw in path.read_text().splitlines():
        line = raw.strip()

        if line.startswith("#"):
            if SECTOR_SEPARATOR in line:
                sector = line.lstrip("# ").split(SECTOR_SEPARATOR)[0].strip()

            continue

        if line:
            universe.setdefault(line.upper(), sector)

    return universe


def read_catalog(path: Path | None) -> dict[str, dict]:
    """
    The canonical security catalogue: one record per Yahoo
    ticker, with name, exchange, sector, currency and the
    index snapshots it belongs to (Russell 2500, STOXX 600).

    Memberships are CURRENT snapshots. Nothing here says a
    company was in an index on a past date, so a replayed desk
    inherits today's survivors, and says so.
    """

    if path is None or not path.is_file():
        return {}

    try:
        records = json.loads(path.read_text())["securities"]
    except (ValueError, KeyError, TypeError):
        return {}

    return {
        str(record["ticker"]).upper(): record
        for record in records
        if record.get("ticker")
    }


class InstrumentRepository:
    """
    Symbol lookup.

    Yahoo's search endpoint resolves free text such as
    "nvidia" to NVDA. The catalogue and the local peer
    universe answer without the network, and are the
    fallback when Yahoo does not.
    """

    def __init__(
        self,
        universe_file: Path,
        *,
        searcher=None,
        catalog_file: Path | None = None,
    ):
        self._catalog = read_catalog(catalog_file)

        # The catalogue's GICS sector wins over a header of the
        # hand-written list.
        self._sectors = {
            **read_universe(universe_file),
            **{
                ticker: record.get("sector")
                for ticker, record in self._catalog.items()
                if record.get("sector")
            },
        }

        for ticker in self._catalog:
            self._sectors.setdefault(ticker, None)

        self._universe = tuple(self._sectors)
        self._search = searcher or self._yahoo_search
        self._described: dict[str, Instrument] = {}

    @property
    def catalog_size(self) -> int:
        return len(self._catalog)

    @property
    def groups(self) -> dict[str, str]:
        """
        Universe and currency of every catalogued security. A
        pair is only looked for inside one group: across
        currencies it would be a bet on the exchange rate.
        """

        return {
            ticker: f"{'+'.join(sorted(record.get('universes') or ['-']))}"
            f"/{record.get('currency') or '-'}"
            for ticker, record in self._catalog.items()
        }

    def _from_catalog(self, record: dict) -> Instrument:
        return Instrument(
            ticker=record["ticker"],
            name=record.get("name") or record["ticker"],
            exchange=record.get("exchange"),
            kind="EQUITY",
            sector=record.get("sector"),
        )

    def _catalog_matches(self, text: str, limit: int) -> list[Instrument]:
        query = text.casefold()

        matches = [
            record
            for ticker, record in self._catalog.items()
            if query in ticker.casefold()
            or query in str(record.get("name", "")).casefold()
        ]

        matches.sort(
            key=lambda r: (
                r["ticker"].casefold() != query,
                not r["ticker"].casefold().startswith(query),
                r["ticker"],
            )
        )

        return [self._from_catalog(record) for record in matches[:limit]]

    @property
    def universe(self) -> tuple[str, ...]:
        return self._universe

    @property
    def sectors(self) -> dict[str, str]:
        """Sector of every universe ticker that has one."""

        return {t: s for t, s in self._sectors.items() if s is not None}

    def search(self, query: str, *, limit: int = 8) -> tuple[Instrument, ...]:
        text = query.strip()

        if not text:
            return ()

        try:
            results = self._search(text, limit)
        except Exception:
            results = ()

        # Being searchable does not depend on being in an index:
        # Yahoo finds what the catalogue lacks, the catalogue
        # answers when Yahoo is down, and an exact ticker match
        # leads either way.
        merged: dict[str, Instrument] = {}

        for instrument in (*results, *self._catalog_matches(text, limit)):
            merged.setdefault(instrument.ticker.upper(), instrument)

        if merged:
            exact = text.upper()

            return tuple(
                sorted(
                    merged.values(),
                    key=lambda i: i.ticker.upper() != exact,
                )
            )[:limit]

        return tuple(
            Instrument(ticker=ticker, name=ticker)
            for ticker in self._universe
            if ticker.startswith(text.upper())
        )[:limit]

    def describe(self, ticker: str) -> Instrument:
        symbol = ticker.strip().upper()

        # No network round trip for three thousand known names.
        if symbol not in self._described and symbol in self._catalog:
            self._described[symbol] = self._from_catalog(self._catalog[symbol])

        if symbol not in self._described:
            self._described[symbol] = next(
                (
                    instrument
                    for instrument in self.search(symbol, limit=5)
                    if instrument.ticker == symbol
                ),
                Instrument(ticker=symbol, name=symbol),
            )

        return self._described[symbol]

    @staticmethod
    def _yahoo_search(query: str, limit: int) -> tuple[Instrument, ...]:
        quotes = yf.Search(
            query,
            max_results=limit * 2,
            news_count=0,
        ).quotes

        return tuple(
            Instrument(
                ticker=quote["symbol"],
                name=(
                    quote.get("longname")
                    or quote.get("shortname")
                    or quote["symbol"]
                ),
                exchange=quote.get("exchDisp"),
                kind=quote.get("quoteType"),
                sector=quote.get("sectorDisp"),
            )
            for quote in quotes
            if quote.get("symbol")
            and quote.get("quoteType") in TRADABLE_KINDS
        )
