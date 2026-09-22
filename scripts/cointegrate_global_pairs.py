"""
Engle-Granger cointegration for every correlated pair of the
global equities universe, on all CPU cores.

    python scripts/cointegrate_global_pairs.py
    python scripts/cointegrate_global_pairs.py --sessions 252 --corr-min 0.8

The screen is the one cointegration.screen_pairs runs, applied
to the whole universe:

- log prices over the formation window (the last --sessions);
- pairs whose daily log-return correlation is above --corr-min;
- both legs I(1): unit root kept in levels, rejected in changes;
- Engle-Granger both ways round, the stronger ordering kept,
  with ticker_a as its dependent leg.

The tests are statsmodels': statsmodels.tsa.stattools.coint for
Engle-Granger, sm.OLS for the hedge ratio and spread it judges,
and is_i1 from anomaly_detection.cointegration.
Pairs are independent, so they are spread over worker processes.

With a GPU (--device auto picks CUDA, then Apple's MPS) the same
tests run batched in PyTorch instead: every series has the same
length, so each ADF regression of a chunk of pairs is one
batched matrix product and one batched solve. Lag selection,
samples, t statistics and MacKinnon p-values follow
statsmodels' adfuller step by step. The hedge ratio, constant
and spread stay in float64 NumPy, which is cheap.

beta is the hedge ratio of the regression on log prices,

    log(A) = const + beta * log(B) + spread

so it is a ratio of dollars, not of shares: $beta of B against
each $1 of A. In shares, beta * price(A) / price(B) of B per
share of A.

The universe spans US and European exchanges, whose holidays
differ. Prices are put on the union of trading days and carried
forward over short closures (--max-gap sessions); a name still
missing a price in the window is left out.
"""

from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.adfvalues import mackinnonp
from statsmodels.tsa.stattools import coint

from financial_assistant.anomaly_detection.cointegration import is_i1


ROOT = Path(__file__).resolve().parents[1]

UNIVERSE = ROOT / "data" / "universes" / "global_equities.csv"
PRICES = ROOT / "data" / "cache" / "market" / "daily"
OUTPUT = ROOT / "data" / "cache" / "cointegration" / "global_pairs.csv"


# --- data ------------------------------------------------------------------


def load_universe(path: Path) -> pd.DataFrame:
    universe = pd.read_csv(path)

    universe = universe[universe["mapping_status"] == "mapped"]

    return universe.drop_duplicates("yahoo_ticker").set_index("yahoo_ticker")


def load_closes(tickers: list[str], directory: Path) -> pd.DataFrame:
    """Wide date x ticker matrix of closes from the daily cache."""

    columns = {}

    for ticker in tickers:
        path = directory / f"{ticker}.csv"

        if not path.exists():
            continue

        frame = pd.read_csv(path, usecols=["date", "close"], parse_dates=["date"])
        columns[ticker] = frame.drop_duplicates("date").set_index("date")["close"]

    return pd.DataFrame(columns).sort_index()


def formation_window(
    closes: pd.DataFrame,
    *,
    sessions: int,
    end: str | None,
    max_gap: int,
) -> pd.DataFrame:
    """
    The last `sessions` trading days up to `end`, carried
    forward over holidays, with only the names that have a
    positive price on every one of them.
    """

    filled = closes.ffill(limit=max_gap)

    if end is not None:
        filled = filled.loc[:end]

    window = filled.iloc[-sessions:]

    complete = window.notna().all() & (window > 0).all()

    return window.loc[:, complete]


# --- tests -----------------------------------------------------------------


# Log prices [names, sessions], set once in each worker process.
_log_px: np.ndarray | None = None


def _init_worker(log_px: np.ndarray) -> None:
    global _log_px
    _log_px = log_px


def _i1(index: int) -> bool:
    return is_i1(pd.Series(_log_px[index]))


def _best_ordering(pair: tuple[int, int]) -> dict | None:
    """
    Engle-Granger is not symmetric: both orderings are tested
    and the one with the lower p-value kept, as screen_pairs
    does. None for a degenerate spread.
    """

    first, second = pair

    tests = [
        (dependent, regressor, *coint(_log_px[dependent], _log_px[regressor], trend="c", autolag="aic")[:2])
        for dependent, regressor in ((first, second), (second, first))
    ]

    dependent, regressor, statistic, pvalue = min(tests, key=lambda t: t[3])

    # coint does not return the cointegrating regression; the
    # same OLS gives the hedge ratio and the spread it tested.
    fit = sm.OLS(_log_px[dependent], sm.add_constant(_log_px[regressor])).fit()
    spread = pd.Series(fit.resid)

    spread_std = float(spread.std())

    if not np.isfinite(spread_std) or spread_std <= 0:
        return None

    return {
        "a": dependent,
        "b": regressor,
        "const": fit.params[0],
        "beta": fit.params[1],
        "adf_stat": statistic,
        "pvalue": pvalue,
        "spread_mean": float(spread.mean()),
        "spread_std": spread_std,
    }


# --- the same tests, batched on a GPU --------------------------------------


def pick_device(wanted: str):
    """
    A torch device for "cuda", "mps" or "auto" (CUDA, then MPS);
    None means the statsmodels path on the CPU.
    """

    if wanted == "cpu":
        return None

    try:
        import torch
    except ImportError:
        if wanted != "auto":
            raise
        return None

    if wanted in ("auto", "cuda") and torch.cuda.is_available():
        # The card with the most free memory: on a shared box
        # the others may be full of model weights.
        free = [torch.cuda.mem_get_info(i)[0] for i in range(torch.cuda.device_count())]
        return torch.device(f"cuda:{free.index(max(free))}")

    if wanted in ("auto", "mps") and torch.backends.mps.is_available():
        return torch.device("mps")

    if wanted != "auto":
        raise SystemExit(f"--device {wanted}: not available")

    return None


def _least_squares(design, target):
    """
    Batched OLS through the normal equations.

        design  [P, n, m]      target  [P, n]

    Returns the coefficients [P, m], the residual sum of squares
    [P] and the first diagonal element of (X'X)^-1 [P], which is
    all the t statistic of the first regressor needs. A singular
    system (a flat price) comes back NaN and is rejected
    downstream without failing its chunk.
    """

    import torch

    gram = design.mT @ design
    moment = (design.mT @ target.unsqueeze(-1)).squeeze(-1)

    unit = torch.zeros_like(moment)
    unit[:, 0] = 1.0

    solved, info = torch.linalg.solve_ex(gram, torch.stack((moment, unit), dim=-1))
    solved = torch.where((info != 0)[:, None, None], torch.nan, solved)

    beta = solved[..., 0]
    residual = target - (design @ beta.unsqueeze(-1)).squeeze(-1)

    return beta, (residual * residual).sum(dim=1), solved[:, 0, 1]


def _default_maxlag(observations: int, trend_terms: int) -> int:
    """statsmodels' rule: 12 * (n / 100) ** 0.25, bounded by the sample."""

    maxlag = int(np.ceil(12.0 * np.power(observations / 100.0, 0.25)))

    return max(0, min(observations // 2 - trend_terms - 1, maxlag))


def _adf_design(series, lags: int, constant: bool):
    """
    The ADF regression for `lags` lagged differences:

        d x[t] = rho * x[t-1] + sum_j g_j * d x[t-j] (+ c) + e[t]

    Column 0 is the lagged level, whose t statistic is the test.
    """

    import torch

    difference = series[:, 1:] - series[:, :-1]
    length = difference.shape[1]
    rows = length - lags

    columns = [series[:, lags:-1]]
    columns += [difference[:, lags - j:length - j] for j in range(1, lags + 1)]

    if constant:
        columns.append(torch.ones_like(columns[0]))

    return torch.stack(columns, dim=-1), difference[:, lags:]


def adf_statistic(series: np.ndarray, *, constant: bool, device) -> np.ndarray:
    """
    statsmodels' adfuller(autolag="AIC") t statistic for every
    row of `series` [P, T]; `constant` is regression="c",
    without it regression="n".

    The statistic does not change when a series is rescaled, nor
    when it is shifted if the regression has a constant. Each row
    is therefore put on unit-variance changes (and centred)
    first, which keeps the normal equations well conditioned in
    float32, the only precision MPS has.
    """

    import torch

    dtype = torch.float32 if device.type == "mps" else torch.float64

    with np.errstate(divide="ignore", invalid="ignore"):
        if constant:
            series = series - series.mean(axis=1, keepdims=True)
        series = series / np.diff(series, axis=1).std(axis=1, keepdims=True)

    x = torch.as_tensor(series, dtype=dtype, device=device)

    pairs, length = x.shape
    maxlag = _default_maxlag(length, 1 if constant else 0)

    # Lag selection: every order on the same sample, the one the
    # longest lag allows, so the criteria are comparable.
    full, target = _adf_design(x, maxlag, constant=False)
    rows = full.shape[1]

    criteria = torch.empty(pairs, maxlag + 1, dtype=dtype, device=device)

    for lag in range(maxlag + 1):
        design = full[:, :, :lag + 1]

        if constant:
            design = torch.cat((design, torch.ones_like(design[:, :, :1])), dim=-1)

        _, ssr, _ = _least_squares(design, target)

        # OLS AIC up to a constant shared by every order.
        criteria[:, lag] = rows * torch.log(ssr / rows) + 2.0 * design.shape[-1]

    # A degenerate row has no finite criterion: lag 0, NaN statistic.
    chosen = torch.where(
        torch.isfinite(criteria).all(dim=1),
        torch.nan_to_num(criteria, nan=torch.inf).argmin(dim=1),
        0,
    )

    # The test itself, re-estimated on the longer sample the
    # chosen order allows. Rows with the same order solve together.
    statistic = torch.empty(pairs, dtype=dtype, device=device)

    for lag in torch.unique(chosen).tolist():
        members = torch.nonzero(chosen == lag).squeeze(1)

        design, response = _adf_design(x[members], lag, constant)
        beta, ssr, inverse = _least_squares(design, response)

        variance = ssr / (design.shape[1] - design.shape[2])
        statistic[members] = beta[:, 0] / torch.sqrt(variance * inverse)

    return statistic.cpu().double().numpy()


def _pvalues(statistics: np.ndarray, series: int) -> np.ndarray:
    return np.array(
        [mackinnonp(s, regression="c", N=series) if np.isfinite(s) else np.nan for s in statistics]
    )


def _chunks(total: int, size: int):
    for start in range(0, total, size):
        yield slice(start, min(start + size, total))


def i1_gpu(log_px: np.ndarray, *, device, chunk: int, alpha: float = 0.05) -> np.ndarray:
    """is_i1 for every row: unit root kept in levels, rejected in changes."""

    verdict = np.zeros(len(log_px), dtype=bool)

    for part in _chunks(len(log_px), chunk):
        levels = log_px[part]

        in_levels = adf_statistic(levels, constant=True, device=device)
        in_changes = adf_statistic(np.diff(levels, axis=1), constant=True, device=device)

        verdict[part] = (_pvalues(in_levels, 1) > alpha) & (_pvalues(in_changes, 1) <= alpha)

    return verdict


def engle_granger_gpu(y: np.ndarray, x: np.ndarray, *, device, chunk: int) -> dict[str, np.ndarray]:
    """
    coint(y, x) for every row pair of two [P, T] arrays: the
    regression y = const + beta * x + spread, then ADF without a
    constant on the spread, judged against MacKinnon's surface
    for two series.
    """

    x_mean = x.mean(axis=1, keepdims=True)
    y_mean = y.mean(axis=1, keepdims=True)
    centred = x - x_mean

    with np.errstate(divide="ignore", invalid="ignore"):
        beta = (centred * (y - y_mean)).sum(axis=1) / (centred * centred).sum(axis=1)
    const = y_mean[:, 0] - beta * x_mean[:, 0]

    spread = y - const[:, None] - beta[:, None] * x

    statistic = np.concatenate(
        [adf_statistic(spread[part], constant=False, device=device) for part in _chunks(len(y), chunk)]
    )

    return {
        "const": const,
        "beta": beta,
        "adf_stat": statistic,
        "pvalue": _pvalues(statistic, 2),
        "spread_mean": spread.mean(axis=1),
        "spread_std": spread.std(axis=1, ddof=1),
    }


def screen_gpu(log_px, first, second, *, device, chunk: int) -> list[dict]:
    """_best_ordering for every pair, batched."""

    count = len(first)

    dependent = np.concatenate((first, second))
    regressor = np.concatenate((second, first))

    parts = [
        engle_granger_gpu(log_px[dependent[part]], log_px[regressor[part]], device=device, chunk=chunk)
        for part in _chunks(len(dependent), 16 * chunk)
    ]
    result = {key: np.concatenate([p[key] for p in parts]) for key in parts[0]}

    forward = np.nan_to_num(result["pvalue"][:count], nan=np.inf)
    backward = np.nan_to_num(result["pvalue"][count:], nan=np.inf)
    best = np.where(backward < forward, np.arange(count) + count, np.arange(count))

    frame = pd.DataFrame(
        {"a": dependent[best], "b": regressor[best], **{key: values[best] for key, values in result.items()}}
    )

    frame = frame[np.isfinite(frame["spread_std"]) & (frame["spread_std"] > 0)]

    return frame.to_dict("records")


# --- the screen ------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])

    parser.add_argument("--universe", type=Path, default=UNIVERSE)
    parser.add_argument("--prices", type=Path, default=PRICES)
    parser.add_argument("--out", type=Path, default=OUTPUT)

    parser.add_argument("--sessions", type=int, default=504, help="formation window, trading days")
    parser.add_argument("--end", default=None, help="last formation date (default: latest cached)")
    parser.add_argument("--max-gap", type=int, default=5, help="sessions a price is carried over a closure")

    parser.add_argument("--corr-min", type=float, default=0.70)
    parser.add_argument("--alpha", type=float, default=0.01)
    parser.add_argument("--no-i1-check", action="store_true")

    parser.add_argument("--device", choices=("auto", "cuda", "mps", "cpu"), default="auto")
    parser.add_argument("--chunk", type=int, default=2048, help="pairs per batched GPU solve")
    parser.add_argument("--workers", type=int, default=os.cpu_count(), help="processes on the CPU path")
    parser.add_argument("--all", action="store_true", help="write every tested pair, not only cointegrated ones")

    args = parser.parse_args()

    device = pick_device(args.device)

    started = time.perf_counter()

    def log(message: str) -> None:
        print(f"[{time.perf_counter() - started:7.1f}s] {message}", flush=True)

    universe = load_universe(args.universe)
    closes = load_closes(list(universe.index), args.prices)

    log(f"{closes.shape[1]} of {len(universe)} names have cached prices")

    window = formation_window(closes, sessions=args.sessions, end=args.end, max_gap=args.max_gap)
    tickers = np.array(window.columns)

    log(
        f"{len(tickers)} names complete over {len(window)} sessions "
        f"{window.index[0].date()} -> {window.index[-1].date()}"
    )

    log_px = np.log(window.to_numpy().T)

    with np.errstate(divide="ignore", invalid="ignore"):
        correlation = np.corrcoef(np.diff(log_px, axis=1))

    first, second = np.triu_indices(len(tickers), k=1)
    keep = correlation[first, second] > args.corr_min
    first, second = first[keep], second[keep]

    log(f"{len(first):,} pairs with return correlation > {args.corr_min}")
    log(f"running on {device or f'cpu ({args.workers} statsmodels workers)'}")

    candidates = np.union1d(first, second)

    if device is not None:
        if not args.no_i1_check:
            i1 = np.zeros(len(tickers), dtype=bool)
            i1[candidates] = i1_gpu(log_px[candidates], device=device, chunk=args.chunk)

            keep = i1[first] & i1[second]
            first, second = first[keep], second[keep]

            log(f"{int(i1.sum())} of {len(candidates)} candidate names I(1); {len(first):,} pairs left")

        results = screen_gpu(log_px, first, second, device=device, chunk=args.chunk)

    else:
        with ProcessPoolExecutor(args.workers, initializer=_init_worker, initargs=(log_px,)) as pool:
            if not args.no_i1_check:
                i1 = np.zeros(len(tickers), dtype=bool)
                i1[candidates] = list(pool.map(_i1, candidates, chunksize=16))

                keep = i1[first] & i1[second]
                first, second = first[keep], second[keep]

                log(f"{int(i1.sum())} of {len(candidates)} candidate names I(1); {len(first):,} pairs left")

            results = list(pool.map(_best_ordering, zip(first, second), chunksize=64))

    log(f"{2 * len(first):,} Engle-Granger tests done")

    pairs = pd.DataFrame([r for r in results if r is not None])

    if pairs.empty:
        log("nothing to report")
        return

    pairs["correlation"] = correlation[pairs["a"], pairs["b"]]
    pairs.insert(0, "ticker_a", tickers[pairs.pop("a")])
    pairs.insert(1, "ticker_b", tickers[pairs.pop("b")])
    pairs["cointegrated"] = pairs["pvalue"] < args.alpha

    for leg in ("a", "b"):
        info = universe.loc[pairs[f"ticker_{leg}"], ["name", "sector", "exchange", "currency"]]
        for column in info.columns:
            pairs[f"{column}_{leg}"] = info[column].to_numpy()

    pairs["formation_start"] = window.index[0].date()
    pairs["formation_end"] = window.index[-1].date()

    pairs = pairs.sort_values("pvalue").reset_index(drop=True)

    cointegrated = pairs[pairs["cointegrated"]]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    (pairs if args.all else cointegrated).to_csv(args.out, index=False)

    log(f"{len(cointegrated):,} of {len(pairs):,} pairs cointegrated at alpha={args.alpha}")
    log(f"wrote {args.out}")

    with pd.option_context("display.width", 160, "display.max_columns", 20):
        print(
            cointegrated[
                ["ticker_a", "ticker_b", "sector_a", "sector_b", "correlation", "beta", "pvalue"]
            ]
            .head(20)
            .to_string(index=False)
        )


if __name__ == "__main__":
    main()
