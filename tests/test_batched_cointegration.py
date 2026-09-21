"""
The batched engine must give statsmodels' numbers: it replaces
tens of thousands of calls to the reference implementation, and
a pair is admitted or rejected on the third decimal of a p-value.
"""

import numpy as np
import pandas as pd
import pytest
from statsmodels.tsa.stattools import adfuller

from financial_assistant.anomaly_detection.batched import (
    adf_batch,
    engle_granger_batch,
    integrated_of_order_one,
)
from financial_assistant.anomaly_detection.cointegration import (
    engle_granger,
    half_life,
    is_i1,
)


def series(count: int = 24, length: int = 504, seed: int = 3) -> np.ndarray:
    """Random walks, stationary series and everything between."""

    rng = np.random.default_rng(seed)
    rows = []

    for index in range(count):
        shocks = rng.normal(0, 0.012, length)
        persistence = (1.0, 0.98, 0.9, 0.5)[index % 4]

        values = np.empty(length)
        values[0] = 4.0

        for t in range(1, length):
            values[t] = 4.0 + persistence * (values[t - 1] - 4.0) + shocks[t]

        rows.append(values)

    return np.array(rows)


@pytest.mark.parametrize("constant", [True, False])
def test_adf_matches_statsmodels_row_by_row(constant):
    data = series()
    batch = adf_batch(data, constant=constant)

    for row, values in enumerate(data):
        statistic, _, lags, observations, _, _ = adfuller(
            values,
            regression="c" if constant else "n",
            autolag="AIC",
            result_object=False,
        )

        assert batch.lags[row] == lags
        assert batch.observations[row] == observations
        assert batch.statistic[row] == pytest.approx(statistic, rel=1e-7, abs=1e-9)


def test_engle_granger_matches_the_reference_pair_by_pair():
    rng = np.random.default_rng(11)
    length = 504

    driver = np.cumsum(rng.normal(0, 0.012, length))

    dependent, regressor = [], []

    for index in range(16):
        x = 4.0 + driver + np.cumsum(rng.normal(0, 0.004, length)) * (index % 2)
        noise = rng.normal(0, 0.006, length)

        # Even rows are cointegrated with x, odd rows are not.
        y = 3.0 + 0.8 * x + noise + np.cumsum(rng.normal(0, 0.01, length)) * (index % 2)

        dependent.append(y)
        regressor.append(x)

    batch = engle_granger_batch(np.array(dependent), np.array(regressor))

    for row, (y, x) in enumerate(zip(dependent, regressor)):
        reference = engle_granger(pd.Series(y), pd.Series(x), check_i1=False)

        assert batch.beta[row] == pytest.approx(reference["beta"], rel=1e-9)
        assert batch.const[row] == pytest.approx(reference["const"], rel=1e-9)
        assert batch.lags[row] == reference["lags"]
        assert batch.observations[row] == reference["nobs"]
        assert batch.statistic[row] == pytest.approx(reference["adf_stat"], rel=1e-7)
        assert batch.pvalue[row] == pytest.approx(reference["pvalue"], rel=1e-6, abs=1e-12)

        spread = reference["spread"]

        assert batch.spread_std[row] == pytest.approx(float(spread.std()), rel=1e-9)
        assert batch.half_life[row] == pytest.approx(half_life(spread), rel=1e-7)

    # The data was built so that both verdicts occur.
    assert (batch.pvalue < 0.05).any() and (batch.pvalue > 0.05).any()


def test_the_integration_order_check_matches_the_reference():
    data = series(count=12)
    verdicts = integrated_of_order_one(data)

    assert list(verdicts) == [is_i1(pd.Series(values)) for values in data]
    assert verdicts.any() and not verdicts.all()


def test_a_degenerate_pair_is_rejected_without_breaking_the_batch():
    """
    Two identical series (one company listed twice) leave a
    spread of zeros and a singular regression. That pair must be
    rejected, and its neighbours in the batch must be untouched.
    """

    rng = np.random.default_rng(2)
    length = 504

    x = 4.0 + np.cumsum(rng.normal(0, 0.012, length))
    healthy = 3.0 + 0.8 * x + rng.normal(0, 0.006, length)

    alone = engle_granger_batch(np.array([healthy]), np.array([x]))
    mixed = engle_granger_batch(np.array([healthy, x]), np.array([x, x]))

    assert mixed.pvalue[0] == pytest.approx(alone.pvalue[0], rel=1e-6)
    assert mixed.statistic[0] == pytest.approx(alone.statistic[0], rel=1e-6)

    # NaN is not below any alpha: the twin pair is never admitted.
    assert not (mixed.pvalue[1] < 0.05)

    flat = np.full((1, length), 4.0)

    assert list(integrated_of_order_one(flat)) == [False]
