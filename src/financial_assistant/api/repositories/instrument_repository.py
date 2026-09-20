from __future__ import annotations

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


class InstrumentRepository:
    """
    Symbol lookup.

    Yahoo's search endpoint resolves free text such as
    "nvidia" to NVDA. The local peer universe is the
    offline fallback.
    """

    def __init__(self, universe_file: Path, *, searcher=None):
        self._sectors = read_universe(universe_file)
        self._universe = tuple(self._sectors)
        self._search = searcher or self._yahoo_search
        self._described: dict[str, Instrument] = {}

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

        if results:
            return results[:limit]

        return tuple(
            Instrument(ticker=ticker, name=ticker)
            for ticker in self._universe
            if ticker.startswith(text.upper())
        )[:limit]

    def describe(self, ticker: str) -> Instrument:
        symbol = ticker.strip().upper()

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
