"""
The desk's Engle-Granger is statsmodels' coint, and spreading
the tests over worker processes changes nothing but the time.
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import coint

from financial_assistant.anomaly_detection import cointegration
from financial_assistant.anomaly_detection.cointegration import (
    engle_granger,
    engle_granger_many,
    integrated,
    is_i1,
)


def walks(count: int, sessions: int = 300, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)

    return 4.0 + np.cumsum(rng.normal(0, 0.01, (count, sessions)), axis=1)


def test_engle_granger_is_statsmodels_coint():
    rng = np.random.default_rng(11)
    x = walks(1)[0]
    y = 0.5 + 0.8 * x + rng.normal(0, 0.005, len(x))

    result = engle_granger(pd.Series(y), pd.Series(x), check_i1=False)

    statistic, pvalue, _ = coint(y, x, trend="c", autolag="aic")
    fit = sm.OLS(y, sm.add_constant(x)).fit()

    assert result["adf_stat"] == statistic
    assert result["pvalue"] == pvalue
    assert result["const"] == fit.params[0]
    assert result["beta"] == fit.params[1]
    assert result["cointegrated"]


def test_worker_processes_give_the_serial_answers(monkeypatch):
    series = walks(24)
    pairs = [(series[i], series[j]) for i in range(8) for j in range(8, 16)]

    monkeypatch.setattr(cointegration, "PARALLEL_ABOVE", 10**9)
    serial_tests = engle_granger_many(pairs)
    serial_i1 = integrated(list(series))

    monkeypatch.setattr(cointegration, "PARALLEL_ABOVE", 0)
    monkeypatch.setenv("PAIRS_WORKERS", "2")
    parallel_tests = engle_granger_many(pairs)
    parallel_i1 = integrated(list(series))

    assert parallel_tests == serial_tests
    assert parallel_i1 == serial_i1 == [is_i1(pd.Series(s)) for s in series]
