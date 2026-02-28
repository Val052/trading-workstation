"""Black-Scholes Greeks calculator — pure math, no external deps beyond scipy."""

from __future__ import annotations

import math
from scipy.stats import norm

# Default risk-free rate (10yr treasury approximation)
DEFAULT_RISK_FREE_RATE = 0.045


def bs_price(
    S: float,
    K: float,
    T: float,
    r: float = DEFAULT_RISK_FREE_RATE,
    sigma: float = 0.25,
    option_type: str = "call",
) -> float:
    """
    Standard Black-Scholes option price.

    S = underlying price, K = strike, T = time to expiry in years,
    r = risk-free rate, sigma = implied volatility.
    """
    if T <= 0:
        # At expiry — return intrinsic value
        if option_type == "call":
            return max(S - K, 0.0)
        return max(K - S, 0.0)

    if sigma <= 0:
        return 0.0

    d1 = _d1(S, K, T, r, sigma)
    d2 = d1 - sigma * math.sqrt(T)

    if option_type == "call":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    else:
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def bs_greeks(
    S: float,
    K: float,
    T: float,
    r: float = DEFAULT_RISK_FREE_RATE,
    sigma: float = 0.25,
    option_type: str = "call",
) -> dict:
    """
    Compute Black-Scholes Greeks.

    Returns dict with delta, gamma, theta (daily $), vega (per 1% IV move), rho.
    """
    if T <= 0 or sigma <= 0:
        # At/past expiry or zero vol
        intrinsic_delta = 0.0
        if T <= 0:
            if option_type == "call":
                intrinsic_delta = 1.0 if S > K else 0.0
            else:
                intrinsic_delta = -1.0 if S < K else 0.0
        return {
            "delta": intrinsic_delta,
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0,
            "rho": 0.0,
        }

    d1 = _d1(S, K, T, r, sigma)
    d2 = d1 - sigma * math.sqrt(T)
    sqrt_T = math.sqrt(T)
    pdf_d1 = norm.pdf(d1)
    exp_rT = math.exp(-r * T)

    # Gamma (same for calls and puts)
    gamma = pdf_d1 / (S * sigma * sqrt_T)

    # Vega (same for calls and puts) — scaled to 1% IV move
    vega = S * pdf_d1 * sqrt_T * 0.01

    if option_type == "call":
        delta = norm.cdf(d1)
        theta_annual = (
            -(S * pdf_d1 * sigma) / (2 * sqrt_T)
            - r * K * exp_rT * norm.cdf(d2)
        )
        rho = K * T * exp_rT * norm.cdf(d2) * 0.01
    else:
        delta = norm.cdf(d1) - 1.0
        theta_annual = (
            -(S * pdf_d1 * sigma) / (2 * sqrt_T)
            + r * K * exp_rT * norm.cdf(-d2)
        )
        rho = -K * T * exp_rT * norm.cdf(-d2) * 0.01

    # Convert theta to daily
    theta_daily = theta_annual / 365.0

    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta_daily, 4),
        "vega": round(vega, 4),
        "rho": round(rho, 4),
    }


def probability_of_profit(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str,
    premium_paid: float,
) -> float:
    """
    Probability that option expires above breakeven.

    For calls: breakeven = K + premium, PoP = P(S > breakeven)
    For puts: breakeven = K - premium, PoP = P(S < breakeven)
    """
    if T <= 0 or sigma <= 0:
        return 0.0

    if option_type == "call":
        breakeven = K + premium_paid
        d2 = _d2(S, breakeven, T, r, sigma)
        return float(norm.cdf(d2))
    else:
        breakeven = K - premium_paid
        d2 = _d2(S, breakeven, T, r, sigma)
        return float(norm.cdf(-d2))


def probability_of_touch(S: float, K: float, T: float, sigma: float) -> float:
    """
    Probability that underlying touches price level K before expiry.
    Approximation: 2 * P(ITM at expiry) — barrier option heuristic.
    """
    if T <= 0 or sigma <= 0:
        return 0.0

    d2 = _d2(S, K, T, DEFAULT_RISK_FREE_RATE, sigma)
    if K > S:
        p_itm = float(norm.cdf(d2))
    else:
        p_itm = float(norm.cdf(-d2))

    return min(2.0 * p_itm, 1.0)


def _d1(S: float, K: float, T: float, r: float, sigma: float) -> float:
    return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))


def _d2(S: float, K: float, T: float, r: float, sigma: float) -> float:
    return _d1(S, K, T, r, sigma) - sigma * math.sqrt(T)
