"""
Engle-Granger for thousands of pairs at once.

cointegration.engle_granger runs statsmodels once per pair:
an OLS, then an ADF test with AIC lag selection, which is
itself eighteen small regressions. A universe scan is tens of
thousands of pairs, so tens of thousands of Python round trips
for arithmetic that is identical in shape every time.

Here the same regressions are done for ALL pairs together.
Every series has the same length, so the design matrices stack
into one [pairs, sessions, columns] array and each regression
becomes a batched matrix product and a batched solve: exactly
what BLAS is for. With PyTorch and a CUDA device that is cuBLAS
on the GPU; without, NumPy on the CPU, which is already a
hundred times faster than the loop.

The numbers are statsmodels' numbers. Lag selection, sample
alignment, the AIC and the t statistic follow
statsmodels.tsa.stattools.adfuller step by step, the p-values
come from the same MacKinnon surfaces, and the tests compare
the two implementations pair by pair.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
from statsmodels.tsa.adfvalues import mackinnonp


# Pairs per batched solve. Bounds memory: a chunk holds
# [chunk, sessions, lags + 2] doubles, ~75 MB at these sizes.
CHUNK = 1024


# Set when the GPU refused the work once (out of memory next to
# three language models, a driver problem): NumPy from then on.
_gpu_failed = False


def _torch_device():
    """
    A CUDA device when PyTorch can see one and the desk was not
    told otherwise (PAIRS_DEVICE=cpu). None means NumPy.

    With several GPUs, "auto" takes the one with the most free
    memory: on the desk's box the cards are mostly full of
    model weights, and this needs only a few hundred megabytes.
    """

    wanted = os.environ.get("PAIRS_DEVICE", "auto").strip().lower()

    if wanted == "cpu" or _gpu_failed:
        return None

    try:
        import torch
    except Exception:
        return None

    if not torch.cuda.is_available():
        return None

    if wanted.startswith("cuda"):
        return torch.device(wanted)

    try:
        free = [
            torch.cuda.mem_get_info(index)[0]
            for index in range(torch.cuda.device_count())
        ]

        return torch.device(f"cuda:{free.index(max(free))}")
    except Exception:
        return torch.device("cuda")


def backend() -> str:
    """Where the batched regressions run: "cuda" or "numpy"."""

    return "cuda" if _torch_device() is not None else "numpy"


def _least_squares(design: np.ndarray, target: np.ndarray):
    """
    Batched OLS through the normal equations.

        design  [P, n, m]      target  [P, n]

    Returns the coefficients [P, m], the residual sum of
    squares [P] and the first diagonal element of (X'X)^-1 [P],
    which is all the t statistic of the first regressor needs.

    The series are log prices and their differences, a few
    hundred observations, well scaled: the normal equations
    lose nothing that matters in double precision, and they
    are the form that batches.
    """

    device = _torch_device()

    if device is not None:
        try:
            return _least_squares_cuda(design, target, device)
        except Exception:
            # Same arithmetic on the CPU rather than a failed scan.
            global _gpu_failed
            _gpu_failed = True

    return _least_squares_numpy(design, target)


def _least_squares_cuda(design: np.ndarray, target: np.ndarray, device):
    import torch

    x = torch.as_tensor(design, dtype=torch.float64, device=device)
    y = torch.as_tensor(target, dtype=torch.float64, device=device)

    gram = torch.einsum("pni,pnj->pij", x, x)
    moment = torch.einsum("pni,pn->pi", x, y)

    unit = torch.zeros_like(moment)
    unit[:, 0] = 1.0

    rhs = torch.stack((moment, unit), dim=-1)

    try:
        solved = torch.linalg.solve(gram, rhs)
    except Exception:
        # See the NumPy branch: a degenerate row in the batch.
        solved = torch.linalg.pinv(gram) @ rhs

    beta = solved[..., 0]
    residual = y - torch.einsum("pni,pi->pn", x, beta)

    return (
        beta.cpu().numpy(),
        (residual * residual).sum(dim=1).cpu().numpy(),
        solved[:, 0, 1].cpu().numpy(),
    )


def _least_squares_numpy(design: np.ndarray, target: np.ndarray):
    gram = np.einsum("pni,pnj->pij", design, design)
    moment = np.einsum("pni,pn->pi", design, target)

    unit = np.zeros_like(moment)
    unit[:, 0] = 1.0

    rhs = np.stack((moment, unit), axis=-1)

    try:
        solved = np.linalg.solve(gram, rhs)
    except np.linalg.LinAlgError:
        # One degenerate row (two identical series, a flat
        # price) makes the whole batch singular. The
        # pseudo-inverse solves the healthy rows identically and
        # leaves the degenerate one with a zero variance, which
        # becomes a NaN statistic and is rejected downstream.
        solved = np.linalg.pinv(gram) @ rhs

    beta = solved[..., 0]
    residual = target - np.einsum("pni,pi->pn", design, beta)

    return beta, (residual * residual).sum(axis=1), solved[:, 0, 1]


def default_maxlag(observations: int, trend_terms: int) -> int:
    """statsmodels' rule: 12 * (n / 100) ** 0.25, bounded by the sample."""

    maxlag = int(np.ceil(12.0 * np.power(observations / 100.0, 0.25)))

    return max(0, min(observations // 2 - trend_terms - 1, maxlag))


def _design(series: np.ndarray, lags: int, constant: bool):
    """
    The ADF regression for `lags` lagged differences:

        d x[t] = rho * x[t-1] + sum_j g_j * d x[t-j] (+ c) + e[t]

    Column 0 is the lagged level, whose t statistic is the
    test. The sample starts after the longest lag, so a
    shorter lag order gets a longer sample, as in statsmodels.
    """

    difference = np.diff(series, axis=1)
    rows = difference.shape[1] - lags

    columns = [series[:, lags:-1]]
    columns += [
        difference[:, lags - j:difference.shape[1] - j]
        for j in range(1, lags + 1)
    ]

    if constant:
        columns.append(np.ones((series.shape[0], rows)))

    return np.stack(columns, axis=-1), difference[:, lags:]


@dataclass(frozen=True)
class AdfBatch:
    statistic: np.ndarray
    lags: np.ndarray
    observations: np.ndarray


def adf_batch(series: np.ndarray, *, constant: bool) -> AdfBatch:
    """
    Augmented Dickey-Fuller with AIC lag selection for every
    row of `series` [P, T]. `constant` is regression="c";
    without it, regression="n" (used on residuals).
    """

    series = np.asarray(series, dtype=float)
    pairs, length = series.shape

    maxlag = default_maxlag(length, 1 if constant else 0)

    # --- lag selection: every order on the SAME sample, the
    # one the longest lag allows, so the AICs are comparable.
    full, target = _design(series, maxlag, constant=False)
    rows = full.shape[1]

    criteria = np.empty((pairs, maxlag + 1))

    for lag in range(maxlag + 1):
        design = full[:, :, :lag + 1]

        if constant:
            design = np.concatenate(
                (design, np.ones((pairs, rows, 1))), axis=-1
            )

        _, ssr, _ = _least_squares(design, target)

        # OLS AIC up to a constant shared by every order.
        with np.errstate(divide="ignore", invalid="ignore"):
            criteria[:, lag] = rows * np.log(ssr / rows) + 2.0 * design.shape[-1]

    # A degenerate row has no finite criterion: give it lag 0,
    # its statistic will be NaN either way.
    chosen = np.where(
        np.isfinite(criteria).all(axis=1),
        np.nan_to_num(criteria, nan=np.inf).argmin(axis=1),
        0,
    )

    # --- the test itself, re-estimated on the longer sample
    # the chosen order allows. Pairs that chose the same order
    # are solved together.
    statistic = np.empty(pairs)

    for lag in np.unique(chosen):
        members = np.flatnonzero(chosen == lag)

        design, response = _design(series[members], int(lag), constant)
        beta, ssr, inverse = _least_squares(design, response)

        variance = ssr / (design.shape[1] - design.shape[2])

        with np.errstate(divide="ignore", invalid="ignore"):
            statistic[members] = beta[:, 0] / np.sqrt(variance * inverse)

    return AdfBatch(
        statistic=statistic,
        lags=chosen.astype(int),
        observations=(length - 1 - chosen).astype(int),
    )


def _chunks(total: int):
    for start in range(0, total, CHUNK):
        yield slice(start, min(start + CHUNK, total))


def integrated_of_order_one(levels: np.ndarray, *, alpha: float = 0.05) -> np.ndarray:
    """
    cointegration.is_i1 for every row: a unit root is not
    rejected in levels and is rejected in first differences.
    """

    levels = np.asarray(levels, dtype=float)
    verdict = np.zeros(levels.shape[0], dtype=bool)

    for part in _chunks(levels.shape[0]):
        in_levels = adf_batch(levels[part], constant=True).statistic
        in_changes = adf_batch(np.diff(levels[part], axis=1), constant=True).statistic

        verdict[part] = [
            bool(
                np.isfinite(a)
                and np.isfinite(b)
                and mackinnonp(a, regression="c", N=1) > alpha
                and mackinnonp(b, regression="c", N=1) <= alpha
            )
            for a, b in zip(in_levels, in_changes)
        ]

    return verdict


@dataclass(frozen=True)
class EngleGrangerBatch:
    const: np.ndarray
    beta: np.ndarray
    statistic: np.ndarray
    pvalue: np.ndarray
    lags: np.ndarray
    observations: np.ndarray
    spread_mean: np.ndarray
    spread_std: np.ndarray
    half_life: np.ndarray


def engle_granger_batch(dependent: np.ndarray, regressor: np.ndarray) -> EngleGrangerBatch:
    """
    cointegration.engle_granger for every row pair of two
    [P, T] arrays of log prices: y = const + beta * x + spread,
    then ADF without a constant on the spread, judged against
    MacKinnon's cointegration surface for two series.
    """

    y = np.asarray(dependent, dtype=float)
    x = np.asarray(regressor, dtype=float)

    # Step 1 has a closed form; no solve needed.
    x_mean = x.mean(axis=1, keepdims=True)
    y_mean = y.mean(axis=1, keepdims=True)

    centred = x - x_mean

    with np.errstate(divide="ignore", invalid="ignore"):
        beta = (centred * (y - y_mean)).sum(axis=1) / (centred * centred).sum(axis=1)
    const = y_mean[:, 0] - beta * x_mean[:, 0]

    spread = y - const[:, None] - beta[:, None] * x

    statistic = np.empty(len(y))
    lags = np.empty(len(y), dtype=int)
    observations = np.empty(len(y), dtype=int)

    for part in _chunks(len(y)):
        result = adf_batch(spread[part], constant=False)

        statistic[part] = result.statistic
        lags[part] = result.lags
        observations[part] = result.observations

    # The residuals were estimated, not observed: the
    # distribution is the cointegration one, for N = 2.
    # NaN (a degenerate pair) is never below alpha: rejected.
    pvalue = np.array(
        [
            mackinnonp(s, regression="c", N=2) if np.isfinite(s) else np.nan
            for s in statistic
        ]
    )

    # Half-life of mean reversion: d s[t] = a + b * s[t-1].
    lagged = spread[:, :-1]
    change = np.diff(spread, axis=1)

    lag_centred = lagged - lagged.mean(axis=1, keepdims=True)

    with np.errstate(divide="ignore", invalid="ignore"):
        speed = (
            lag_centred * (change - change.mean(axis=1, keepdims=True))
        ).sum(axis=1) / (lag_centred * lag_centred).sum(axis=1)

    with np.errstate(divide="ignore", invalid="ignore"):
        half_life = np.where(speed < 0, -np.log(2.0) / speed, np.inf)

    return EngleGrangerBatch(
        const=const,
        beta=beta,
        statistic=statistic,
        pvalue=pvalue,
        lags=lags,
        observations=observations,
        spread_mean=spread.mean(axis=1),
        # pandas' Series.std: the sample standard deviation.
        spread_std=spread.std(axis=1, ddof=1),
        half_life=half_life,
    )
