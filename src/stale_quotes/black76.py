"""Black-76 pricing, greeks, implied vol and post-move fair value for ES options.

Conventions
- F: futures price, K: strike, T: time to expiry in years, sigma: annualised vol.
- r: continuously compounded rate used only for discounting. Over minutes it is
  negligible for 0DTE, so it defaults to 0.
- T uses calendar time (ACT/365). Delta and fair value depend on sigma*sqrt(T),
  which is fixed by the market price, so they do not depend on the year
  convention. Only the level of the reported implied vol does.
"""

import math

import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

MINUTES_PER_YEAR = 365 * 24 * 60
SIGMA_MIN = 1e-6
SIGMA_MAX = 10.0


def time_to_expiry(ts, expiry):
    """Years between two tz-aware timestamps (ACT/365). Negative after expiry."""
    ts, expiry = pd.Timestamp(ts), pd.Timestamp(expiry)
    if ts.tzinfo is None or expiry.tzinfo is None:
        raise ValueError("timestamps must be tz-aware")
    return (expiry - ts).total_seconds() / 60 / MINUTES_PER_YEAR


def _d1_d2(F, K, T, sigma):
    v = sigma * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * v * v) / v
    return d1, d1 - v


def price(F, K, T, sigma, is_call, r=0.0):
    df = math.exp(-r * T)
    d1, d2 = _d1_d2(F, K, T, sigma)
    if is_call:
        return df * (F * norm.cdf(d1) - K * norm.cdf(d2))
    return df * (K * norm.cdf(-d2) - F * norm.cdf(-d1))


def delta(F, K, T, sigma, is_call, r=0.0):
    df = math.exp(-r * T)
    d1, _ = _d1_d2(F, K, T, sigma)
    return df * norm.cdf(d1) if is_call else -df * norm.cdf(-d1)


def gamma(F, K, T, sigma, r=0.0):
    df = math.exp(-r * T)
    d1, _ = _d1_d2(F, K, T, sigma)
    return df * norm.pdf(d1) / (F * sigma * math.sqrt(T))


def vega(F, K, T, sigma, r=0.0):
    """Price change per unit (1.00 = 100 vol points) change in sigma."""
    df = math.exp(-r * T)
    d1, _ = _d1_d2(F, K, T, sigma)
    return df * F * norm.pdf(d1) * math.sqrt(T)


def no_arbitrage_bounds(F, K, T, is_call, r=0.0):
    df = math.exp(-r * T)
    if is_call:
        return df * max(F - K, 0.0), df * F
    return df * max(K - F, 0.0), df * K


def implied_vol(px, F, K, T, is_call, r=0.0, min_vega=0.0):
    """Return (sigma, reason). sigma is NaN and reason explains why when the
    price cannot be inverted reliably; reason is None on success."""
    if not (F > 0 and K > 0 and px > 0):
        return math.nan, "non_positive_input"
    if not T > 0:
        return math.nan, "expired"
    lo, hi = no_arbitrage_bounds(F, K, T, is_call, r)
    if px <= lo:
        return math.nan, "below_intrinsic"
    if px >= hi:
        return math.nan, "above_upper_bound"

    def f(s):
        return price(F, K, T, s, is_call, r) - px

    if f(SIGMA_MIN) * f(SIGMA_MAX) > 0:
        return math.nan, "no_solution"
    sigma = brentq(f, SIGMA_MIN, SIGMA_MAX, xtol=1e-12, rtol=1e-12, maxiter=200)
    if vega(F, K, T, sigma, r) < min_vega:
        return math.nan, "low_vega"
    return sigma, None


def fair_value_delta(mid, delta_, dF):
    return mid + delta_ * dF


def fair_value_delta_gamma(mid, delta_, gamma_, dF):
    return mid + delta_ * dF + 0.5 * gamma_ * dF * dF


def fair_value(mid, F0, F1, K, T, is_call, r=0.0, use_gamma=False, min_vega=0.0):
    """Post-move fair value from the pre-move mid (README: Method, fair value).

    Inverts the implied vol from `mid` at futures price `F0`, then shifts `mid`
    by delta (and optionally gamma) times the futures move F1 - F0.
    Returns (fair, sigma, reason); fair and sigma are NaN when reason is set.
    """
    sigma, reason = implied_vol(mid, F0, K, T, is_call, r, min_vega)
    if reason:
        return math.nan, math.nan, reason
    dF = F1 - F0
    d = delta(F0, K, T, sigma, is_call, r)
    if use_gamma:
        return fair_value_delta_gamma(mid, d, gamma(F0, K, T, sigma, r), dF), sigma, None
    return fair_value_delta(mid, d, dF), sigma, None
