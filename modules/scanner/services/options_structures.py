"""Options trade structure comparison engine — stock vs calls vs spreads."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, asdict
from typing import Optional

from modules.scanner.services.options_greeks import (
    bs_price,
    bs_greeks,
    probability_of_profit,
    probability_of_touch,
    DEFAULT_RISK_FREE_RATE,
)
from modules.scanner.services.options_chain import (
    select_expiry,
    select_strikes,
)
from modules.scanner.services.risk_calculator import calculate_risk

logger = logging.getLogger(__name__)


@dataclass
class StructureAnalysis:
    """One complete trade structure analysis."""
    structure_type: str
    display_name: str

    # Position
    contracts: int
    contract_size: int
    total_units: int

    # Legs
    legs: list

    # Risk/Reward
    max_risk: float
    max_reward: Optional[float]
    breakeven: Optional[float]
    risk_reward_ratio: Optional[float]

    # Position sizing
    capital_required: float
    capital_as_pct: float
    risk_as_pct: float

    # Probabilities
    prob_profit: Optional[float]
    prob_target: Optional[float]
    prob_max_loss: Optional[float]

    # Greeks (position-level)
    position_delta: float
    position_gamma: float
    position_theta: float
    position_vega: float

    # Time decay
    theta_as_pct_of_risk: float

    # Scoring
    score: float
    score_rationale: str

    # Expiry info
    expiry: Optional[str]
    dte: Optional[int]

    def to_dict(self) -> dict:
        d = asdict(self)
        # Round floats for clean JSON
        for key, val in d.items():
            if isinstance(val, float):
                d[key] = round(val, 4)
        return d


def compare_structures(
    ticker: str,
    entry: float,
    stop: float,
    target: float,
    account_size: float,
    risk_per_trade: float,
    chains_data: dict,
) -> dict:
    """
    Build all 4 structures side by side and score them.

    Returns dict with ticker, setup, structures list, recommendation, warnings.
    """
    underlying = chains_data.get("underlying_price", entry)
    max_dollar_risk = account_size * risk_per_trade

    structures = []

    # 1. Stock (always available)
    stock = _build_stock(entry, stop, target, account_size, risk_per_trade)
    structures.append(stock)
    stock_capital = stock.capital_required

    # 2-4. Options structures (only if chains available)
    chains = chains_data.get("chains", {})
    if chains:
        # Select best expiry
        hold_days = 10  # default swing trade hold
        target_dte = max(int(2.5 * hold_days), 21)
        expiry = select_expiry(chains, target_dte)

        if expiry and expiry in chains:
            chain = chains[expiry]
            dte = chain["dte"]
            T = dte / 365.0

            # Long Call
            lc = _build_long_call(entry, stop, target, account_size, risk_per_trade, chain, underlying, expiry, dte, T)
            if lc:
                structures.append(lc)

            # Bull Call Spread
            bcs = _build_bull_call_spread(entry, stop, target, account_size, risk_per_trade, chain, underlying, expiry, dte, T)
            if bcs:
                structures.append(bcs)

            # Bull Put Spread
            bps = _build_bull_put_spread(entry, stop, target, account_size, risk_per_trade, chain, underlying, expiry, dte, T)
            if bps:
                structures.append(bps)

    # Score all structures
    _score_structures(structures, stock_capital, target, underlying)

    # Find recommendation
    best = max(structures, key=lambda s: s.score)
    recommendation = {
        "best": best.structure_type,
        "rationale": best.score_rationale,
    }

    # Generate warnings
    warnings = _generate_warnings(ticker, chains_data, structures)

    return {
        "ticker": ticker,
        "underlying_price": underlying,
        "setup": {"entry": entry, "stop": stop, "target": target},
        "structures": [s.to_dict() for s in structures],
        "recommendation": recommendation,
        "warnings": warnings,
    }


def _build_stock(
    entry: float,
    stop: float,
    target: float,
    account_size: float,
    risk_per_trade: float,
) -> StructureAnalysis:
    """Build stock position structure."""
    calc = calculate_risk(entry, stop, target, account_size, risk_per_trade)
    shares = calc.position_size
    capital = shares * entry

    return StructureAnalysis(
        structure_type="stock",
        display_name="Stock",
        contracts=shares,
        contract_size=1,
        total_units=shares,
        legs=[{
            "type": "stock",
            "action": "buy",
            "price": entry,
            "quantity": shares,
        }],
        max_risk=calc.dollar_risk,
        max_reward=calc.dollar_reward,
        breakeven=entry,
        risk_reward_ratio=calc.r_multiple,
        capital_required=capital,
        capital_as_pct=capital / account_size if account_size > 0 else 0,
        risk_as_pct=calc.account_risk_pct,
        prob_profit=None,
        prob_target=None,
        prob_max_loss=None,
        position_delta=float(shares),
        position_gamma=0.0,
        position_theta=0.0,
        position_vega=0.0,
        theta_as_pct_of_risk=0.0,
        score=50.0,  # baseline
        score_rationale="Baseline reference — direct stock exposure with no time decay.",
        expiry=None,
        dte=None,
    )


def _build_long_call(
    entry: float,
    stop: float,
    target: float,
    account_size: float,
    risk_per_trade: float,
    chain: dict,
    underlying: float,
    expiry: str,
    dte: int,
    T: float,
) -> Optional[StructureAnalysis]:
    """Build long call structure."""
    strikes = select_strikes(chain, underlying, "long_call", stop, target)
    if "long" not in strikes:
        return None

    contract = strikes["long"]
    strike = contract["strike"]
    ask_price = contract["ask"]
    iv = contract["iv"]

    if ask_price <= 0:
        return None

    max_dollar_risk = account_size * risk_per_trade
    contracts = max(1, int(max_dollar_risk / (ask_price * 100)))
    total_cost = contracts * ask_price * 100

    # Ensure we don't exceed risk budget
    if total_cost > max_dollar_risk * 1.5:
        contracts = max(1, int(max_dollar_risk / (ask_price * 100)))
        total_cost = contracts * ask_price * 100

    # Reward at target
    target_value = max(target - strike, 0) * contracts * 100
    reward_at_target = target_value - total_cost

    breakeven = strike + ask_price

    # Probabilities
    pop = probability_of_profit(underlying, strike, T, DEFAULT_RISK_FREE_RATE, iv, "call", ask_price)
    p_target = probability_of_touch(underlying, target, T, iv)

    # Position Greeks
    greeks = contract.copy()
    pos_delta = greeks.get("delta", 0) * contracts * 100
    pos_gamma = greeks.get("gamma", 0) * contracts * 100
    pos_theta = greeks.get("theta", 0) * contracts * 100
    pos_vega = greeks.get("vega", 0) * contracts * 100

    theta_pct = abs(pos_theta / total_cost) if total_cost > 0 else 0

    return StructureAnalysis(
        structure_type="long_call",
        display_name="Long Call",
        contracts=contracts,
        contract_size=100,
        total_units=contracts * 100,
        legs=[{
            "type": "call",
            "action": "buy",
            "strike": strike,
            "expiry": expiry,
            "price": ask_price,
            "iv": iv,
            "greeks": {k: greeks[k] for k in ("delta", "gamma", "theta", "vega") if k in greeks},
        }],
        max_risk=total_cost,
        max_reward=reward_at_target if reward_at_target > 0 else None,
        breakeven=breakeven,
        risk_reward_ratio=round(reward_at_target / total_cost, 2) if total_cost > 0 and reward_at_target > 0 else 0,
        capital_required=total_cost,
        capital_as_pct=total_cost / account_size if account_size > 0 else 0,
        risk_as_pct=total_cost / account_size if account_size > 0 else 0,
        prob_profit=round(pop, 4),
        prob_target=round(p_target, 4),
        prob_max_loss=round(1 - pop, 4),
        position_delta=round(pos_delta, 2),
        position_gamma=round(pos_gamma, 4),
        position_theta=round(pos_theta, 2),
        position_vega=round(pos_vega, 2),
        theta_as_pct_of_risk=round(theta_pct, 4),
        score=0.0,  # scored later
        score_rationale="",
        expiry=expiry,
        dte=dte,
    )


def _build_bull_call_spread(
    entry: float,
    stop: float,
    target: float,
    account_size: float,
    risk_per_trade: float,
    chain: dict,
    underlying: float,
    expiry: str,
    dte: int,
    T: float,
) -> Optional[StructureAnalysis]:
    """Build bull call spread (debit spread)."""
    strikes = select_strikes(chain, underlying, "bull_call_spread", stop, target)
    if "long" not in strikes or "short" not in strikes:
        return None

    long_c = strikes["long"]
    short_c = strikes["short"]

    long_ask = long_c["ask"]
    short_bid = short_c["bid"]
    net_debit = long_ask - short_bid

    if net_debit <= 0:
        return None

    strike_width = short_c["strike"] - long_c["strike"]
    if strike_width <= 0:
        return None

    max_dollar_risk = account_size * risk_per_trade
    contracts = max(1, int(max_dollar_risk / (net_debit * 100)))
    total_risk = contracts * net_debit * 100
    max_reward = contracts * (strike_width - net_debit) * 100

    breakeven = long_c["strike"] + net_debit

    # Probabilities
    long_iv = long_c.get("iv", 0.25)
    pop = probability_of_profit(underlying, long_c["strike"], T, DEFAULT_RISK_FREE_RATE, long_iv, "call", net_debit)
    p_max_profit = probability_of_touch(underlying, short_c["strike"], T, long_iv)

    # Position Greeks (net)
    pos_delta = (long_c.get("delta", 0) - short_c.get("delta", 0)) * contracts * 100
    pos_gamma = (long_c.get("gamma", 0) - short_c.get("gamma", 0)) * contracts * 100
    pos_theta = (long_c.get("theta", 0) - short_c.get("theta", 0)) * contracts * 100
    pos_vega = (long_c.get("vega", 0) - short_c.get("vega", 0)) * contracts * 100

    theta_pct = abs(pos_theta / total_risk) if total_risk > 0 else 0

    return StructureAnalysis(
        structure_type="bull_call_spread",
        display_name="Bull Call Spread",
        contracts=contracts,
        contract_size=100,
        total_units=contracts * 100,
        legs=[
            {
                "type": "call", "action": "buy",
                "strike": long_c["strike"], "expiry": expiry,
                "price": long_ask, "iv": long_c.get("iv", 0),
                "greeks": {k: long_c[k] for k in ("delta", "gamma", "theta", "vega") if k in long_c},
            },
            {
                "type": "call", "action": "sell",
                "strike": short_c["strike"], "expiry": expiry,
                "price": short_bid, "iv": short_c.get("iv", 0),
                "greeks": {k: short_c[k] for k in ("delta", "gamma", "theta", "vega") if k in short_c},
            },
        ],
        max_risk=total_risk,
        max_reward=max_reward,
        breakeven=breakeven,
        risk_reward_ratio=round(max_reward / total_risk, 2) if total_risk > 0 else 0,
        capital_required=total_risk,
        capital_as_pct=total_risk / account_size if account_size > 0 else 0,
        risk_as_pct=total_risk / account_size if account_size > 0 else 0,
        prob_profit=round(pop, 4),
        prob_target=round(p_max_profit, 4),
        prob_max_loss=round(1 - pop, 4),
        position_delta=round(pos_delta, 2),
        position_gamma=round(pos_gamma, 4),
        position_theta=round(pos_theta, 2),
        position_vega=round(pos_vega, 2),
        theta_as_pct_of_risk=round(theta_pct, 4),
        score=0.0,
        score_rationale="",
        expiry=expiry,
        dte=dte,
    )


def _build_bull_put_spread(
    entry: float,
    stop: float,
    target: float,
    account_size: float,
    risk_per_trade: float,
    chain: dict,
    underlying: float,
    expiry: str,
    dte: int,
    T: float,
) -> Optional[StructureAnalysis]:
    """Build bull put spread (credit spread)."""
    strikes = select_strikes(chain, underlying, "bull_put_spread", stop, target)
    if "short" not in strikes or "long" not in strikes:
        return None

    short_p = strikes["short"]
    long_p = strikes["long"]

    short_bid = short_p["bid"]
    long_ask = long_p["ask"]
    net_credit = short_bid - long_ask

    if net_credit <= 0:
        return None

    strike_width = short_p["strike"] - long_p["strike"]
    if strike_width <= 0:
        return None

    max_dollar_risk_budget = account_size * risk_per_trade
    risk_per_contract = (strike_width - net_credit) * 100
    if risk_per_contract <= 0:
        return None

    contracts = max(1, int(max_dollar_risk_budget / risk_per_contract))
    total_risk = contracts * risk_per_contract
    max_reward = contracts * net_credit * 100

    breakeven = short_p["strike"] - net_credit

    # Probabilities — P(S > breakeven) at expiry
    short_iv = short_p.get("iv", 0.25)
    # For bull put spread, profit if S stays above breakeven
    d2 = 0
    if short_iv > 0 and T > 0:
        import math
        from scipy.stats import norm
        d2_val = (math.log(underlying / breakeven) + (DEFAULT_RISK_FREE_RATE - 0.5 * short_iv**2) * T) / (short_iv * math.sqrt(T))
        pop = float(norm.cdf(d2_val))
    else:
        pop = 0.5

    p_max_profit = probability_of_touch(underlying, short_p["strike"], T, short_iv)
    # For credit spread, max profit if S > short strike — use 1 - P(touch below)
    p_max_profit = pop  # Approximation: same as PoP for OTM credit spreads

    # Position Greeks (net: short put - long put)
    pos_delta = (short_p.get("delta", 0) - long_p.get("delta", 0)) * contracts * 100
    # Short put has negative delta, we sold it, so net delta is positive
    pos_delta = abs(pos_delta)  # Bull put spread has positive delta
    pos_gamma = (short_p.get("gamma", 0) - long_p.get("gamma", 0)) * contracts * 100
    pos_theta = -(short_p.get("theta", 0) - long_p.get("theta", 0)) * contracts * 100  # Positive for credit
    pos_vega = (short_p.get("theta", 0) - long_p.get("vega", 0)) * contracts * 100

    # Fix vega calc
    pos_vega = -(short_p.get("vega", 0) - long_p.get("vega", 0)) * contracts * 100

    theta_pct = pos_theta / total_risk if total_risk > 0 else 0

    return StructureAnalysis(
        structure_type="bull_put_spread",
        display_name="Bull Put Spread",
        contracts=contracts,
        contract_size=100,
        total_units=contracts * 100,
        legs=[
            {
                "type": "put", "action": "sell",
                "strike": short_p["strike"], "expiry": expiry,
                "price": short_bid, "iv": short_p.get("iv", 0),
                "greeks": {k: short_p[k] for k in ("delta", "gamma", "theta", "vega") if k in short_p},
            },
            {
                "type": "put", "action": "buy",
                "strike": long_p["strike"], "expiry": expiry,
                "price": long_ask, "iv": long_p.get("iv", 0),
                "greeks": {k: long_p[k] for k in ("delta", "gamma", "theta", "vega") if k in long_p},
            },
        ],
        max_risk=total_risk,
        max_reward=max_reward,
        breakeven=breakeven,
        risk_reward_ratio=round(max_reward / total_risk, 2) if total_risk > 0 else 0,
        capital_required=total_risk,
        capital_as_pct=total_risk / account_size if account_size > 0 else 0,
        risk_as_pct=total_risk / account_size if account_size > 0 else 0,
        prob_profit=round(pop, 4),
        prob_target=round(p_max_profit, 4),
        prob_max_loss=round(1 - pop, 4),
        position_delta=round(pos_delta, 2),
        position_gamma=round(pos_gamma, 4),
        position_theta=round(pos_theta, 2),
        position_vega=round(pos_vega, 2),
        theta_as_pct_of_risk=round(theta_pct, 4),
        score=0.0,
        score_rationale="",
        expiry=expiry,
        dte=dte,
    )


def _score_structures(
    structures: list,
    stock_capital: float,
    target: float,
    underlying: float,
) -> None:
    """Score each structure 0-100. Stock always = 50 baseline."""
    for s in structures:
        if s.structure_type == "stock":
            s.score = 50.0
            s.score_rationale = "Baseline reference — direct stock exposure with no time decay."
            continue

        # Components (each 0-1)
        # 1. Risk/reward ratio (25%)
        rr = s.risk_reward_ratio or 0
        norm_rr = min(rr / 5.0, 1.0)

        # 2. Probability of profit (20%)
        norm_pop = s.prob_profit or 0

        # 3. Capital efficiency (20%)
        cap_eff = 1.0 - (s.capital_required / stock_capital) if stock_capital > 0 else 0
        cap_eff = max(0, min(cap_eff, 1.0))

        # 4. Theta efficiency (15%)
        if s.position_theta > 0:
            theta_eff = 1.0  # Positive theta = premium seller, great
        else:
            theta_eff = max(0, 1.0 - abs(s.theta_as_pct_of_risk) * 10)

        # 5. Liquidity score (10%)
        liq = _compute_liquidity_score(s.legs)

        # 6. Probability of target (10%)
        p_tgt = s.prob_target or 0

        score = (
            25 * norm_rr +
            20 * norm_pop +
            20 * cap_eff +
            15 * theta_eff +
            10 * liq +
            10 * p_tgt
        )

        s.score = round(score, 1)

        # Build rationale
        parts = []
        if rr >= 2:
            parts.append(f"R:R {rr:.1f}:1")
        if s.prob_profit and s.prob_profit > 0.5:
            parts.append(f"PoP {s.prob_profit*100:.0f}%")
        if cap_eff > 0.5:
            parts.append("capital efficient")
        if s.position_theta > 0:
            parts.append("positive theta")
        elif s.position_theta < 0 and abs(s.theta_as_pct_of_risk) < 0.02:
            parts.append("manageable decay")

        s.score_rationale = ". ".join(parts) + "." if parts else "Moderate profile."


def _compute_liquidity_score(legs: list) -> float:
    """Score liquidity of all legs 0-1."""
    if not legs:
        return 0.5

    scores = []
    for leg in legs:
        if leg.get("type") == "stock":
            scores.append(1.0)
            continue

        bid = leg.get("price", 0)
        ask = bid  # We store the execution price, approximate
        oi = 0  # We don't carry OI on leg dict, use heuristic
        # If we got this far, the strike passed liquidity filter
        scores.append(0.7)

    return sum(scores) / len(scores) if scores else 0.5


def _generate_warnings(
    ticker: str,
    chains_data: dict,
    structures: list,
) -> list:
    """Generate warnings about the analysis."""
    warnings = []

    # Check if only stock returned (no options)
    options_structures = [s for s in structures if s.structure_type != "stock"]
    if not options_structures:
        warnings.append(f"Options market illiquid or unavailable for {ticker} — stock position only.")

    # Check for zero-contract structures
    for s in structures:
        if s.contracts == 0 and s.structure_type != "stock":
            warnings.append(f"Account risk budget too small for {s.display_name} on {ticker}.")

    # Check bid-ask spreads on legs
    for s in structures:
        for leg in s.legs:
            if leg.get("type") == "stock":
                continue
            # Approximate spread check using IV as proxy for spread width
            iv = leg.get("iv", 0)
            if iv > 0.5:
                warnings.append(f"Elevated IV ({iv:.0%}) on {leg.get('strike', '?')} {leg.get('type', '?')} — options are expensive.")
                break

    # IV level warning
    chains = chains_data.get("chains", {})
    if chains:
        # Sample IV from first chain's ATM options
        first_chain = next(iter(chains.values()), {})
        calls = first_chain.get("calls", [])
        if calls:
            ivs = [c["iv"] for c in calls if c.get("iv", 0) > 0]
            if ivs:
                avg_iv = sum(ivs) / len(ivs)
                if avg_iv > 0.45:
                    warnings.append(f"Average IV is {avg_iv:.0%} — elevated. Consider selling premium (credit spreads).")
                elif avg_iv < 0.15:
                    warnings.append(f"Average IV is {avg_iv:.0%} — low. Buying premium is favorable.")

    # Earnings warning — try to get from yfinance
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        earnings_date = info.get("earningsDate")
        if earnings_date:
            for s in structures:
                if s.expiry and earnings_date:
                    # earningsDate can be timestamp or list
                    pass  # Complex to parse reliably, skip for now
    except Exception:
        pass

    return warnings


def calculate_options_risk(structure: dict, account_size: float) -> dict:
    """
    Format structure data for Candidate.options_analysis JSON field.
    Takes a structure dict (from StructureAnalysis.to_dict()) and returns
    the bookmark-ready format.
    """
    return {
        "structure_type": structure.get("structure_type"),
        "legs": structure.get("legs", []),
        "contracts": structure.get("contracts"),
        "max_risk": structure.get("max_risk"),
        "max_reward": structure.get("max_reward"),
        "breakeven": structure.get("breakeven"),
        "risk_reward_ratio": structure.get("risk_reward_ratio"),
        "account_risk_pct": structure.get("risk_as_pct"),
        "capital_required": structure.get("capital_required"),
        "greeks": {
            "delta": structure.get("position_delta"),
            "theta": structure.get("position_theta"),
            "vega": structure.get("position_vega"),
        },
        "expiry": structure.get("expiry"),
        "dte": structure.get("dte"),
        "prob_profit": structure.get("prob_profit"),
        "score": structure.get("score"),
    }
