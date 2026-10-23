import math

import pandas as pd
import pytest

from stale_quotes import black76 as b

ONE_HOUR = 1 / (365 * 24)


# Benchmarks from the textbooks (independently published values).
def test_haug_benchmark():
    # Haug, Complete Guide to Option Pricing Formulas: F=K=19, T=0.75, r=10%, vol 28%
    assert b.price(19, 19, 0.75, 0.28, True, 0.10) == pytest.approx(1.7011, abs=1e-4)
    assert b.price(19, 19, 0.75, 0.28, False, 0.10) == pytest.approx(1.7011, abs=1e-4)


def test_hull_benchmark():
    # Hull, Options, Futures and Other Derivatives: F=K=20, T=4m, r=9%, vol 25%
    assert b.price(20, 20, 4 / 12, 0.25, False, 0.09) == pytest.approx(1.12, abs=5e-3)


@pytest.mark.parametrize("K", [7800, 7835, 7870])
def test_put_call_parity(K):
    F, T, s, r = 7835.0, ONE_HOUR, 0.15, 0.04
    lhs = b.price(F, K, T, s, True, r) - b.price(F, K, T, s, False, r)
    assert lhs == pytest.approx(math.exp(-r * T) * (F - K), abs=1e-9)


@pytest.mark.parametrize("is_call", [True, False])
@pytest.mark.parametrize("K", [7810, 7835, 7860])
@pytest.mark.parametrize("T", [ONE_HOUR / 4, ONE_HOUR, 6 * ONE_HOUR, 0.25])
def test_implied_vol_round_trip(is_call, K, T):
    F, s = 7835.0, 0.14
    px = b.price(F, K, T, s, is_call)
    sigma, reason = b.implied_vol(px, F, K, T, is_call)
    assert reason is None
    assert sigma == pytest.approx(s, rel=1e-8)


@pytest.mark.parametrize("is_call", [True, False])
def test_delta_and_gamma_match_finite_differences(is_call):
    F, K, T, s, h = 7835.0, 7840, ONE_HOUR, 0.14, 0.01
    up, dn = b.price(F + h, K, T, s, is_call), b.price(F - h, K, T, s, is_call)
    mid = b.price(F, K, T, s, is_call)
    assert b.delta(F, K, T, s, is_call) == pytest.approx((up - dn) / (2 * h), rel=1e-6)
    assert b.gamma(F, K, T, s) == pytest.approx((up - 2 * mid + dn) / h**2, rel=1e-4)


def test_atm_delta_is_half():
    assert b.delta(7835, 7835, ONE_HOUR, 0.14, True) == pytest.approx(0.5, abs=1e-3)
    assert b.delta(7835, 7835, ONE_HOUR, 0.14, False) == pytest.approx(-0.5, abs=1e-3)


@pytest.mark.parametrize(
    "px, T, is_call, reason",
    [
        (4.99, ONE_HOUR, True, "below_intrinsic"),  # call K=7830 worth >= 5
        (7835.0, ONE_HOUR, True, "above_upper_bound"),
        (5.5, 0.0, True, "expired"),
        (5.5, -ONE_HOUR, True, "expired"),
        (0.0, ONE_HOUR, False, "non_positive_input"),
    ],
)
def test_implied_vol_invalid_inputs(px, T, is_call, reason):
    sigma, got = b.implied_vol(px, 7835.0, 7830, T, is_call)
    assert math.isnan(sigma)
    assert got == reason


def test_low_vega_rejected():
    # OTM call one minute before expiry: price barely responds to vol
    # (vega ~0.04 vs ~4.3 at the money), so the inverted vol is unreliable.
    F, K, T = 7835.0, 7845, 1 / (365 * 24 * 60)
    px = b.price(F, K, T, 0.3, True)
    assert b.implied_vol(px, F, K, T, True)[1] is None  # no threshold: accepted
    sigma, reason = b.implied_vol(px, F, K, T, True, min_vega=0.1)
    assert math.isnan(sigma) and reason == "low_vega"


def test_fair_value_delta_shift():
    F0, K, T, s = 7835.0, 7835, ONE_HOUR, 0.14
    mid = b.price(F0, K, T, s, True)
    fair, sigma, reason = b.fair_value(mid, F0, F0 + 1.0, K, T, True)
    assert reason is None and sigma == pytest.approx(s)
    assert fair == pytest.approx(mid + b.delta(F0, K, T, s, True) * 1.0)


def test_fair_value_invalid_propagates():
    fair, sigma, reason = b.fair_value(0.01, 7835.0, 7836.0, 7700, ONE_HOUR, True)
    assert math.isnan(fair) and math.isnan(sigma) and reason == "below_intrinsic"


@pytest.mark.parametrize("ticks", [1, 4, 8])
def test_delta_gamma_closer_than_delta_for_multi_tick_moves(ticks):
    # Near-ATM 0DTE: gamma is large, so delta-only misses more as moves grow.
    F0, K, T, s = 7835.0, 7835, ONE_HOUR, 0.14
    dF = 0.25 * ticks
    mid = b.price(F0, K, T, s, True)
    exact = b.price(F0 + dF, K, T, s, True)
    fd, _, _ = b.fair_value(mid, F0, F0 + dF, K, T, True)
    fdg, _, _ = b.fair_value(mid, F0, F0 + dF, K, T, True, use_gamma=True)
    assert abs(fdg - exact) < abs(fd - exact)


def test_time_to_expiry():
    expiry = pd.Timestamp("2026-10-07 16:00", tz="America/New_York")
    ts = pd.Timestamp("2026-10-07 14:00", tz="America/Chicago")  # 15:00 ET
    assert b.time_to_expiry(ts, expiry) == pytest.approx(ONE_HOUR)
    with pytest.raises(ValueError):
        b.time_to_expiry(pd.Timestamp("2026-10-07 15:00"), expiry)
