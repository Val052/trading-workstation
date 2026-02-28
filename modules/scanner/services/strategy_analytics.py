"""Strategy analytics — aggregated performance stats from outcome data."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from modules.scanner.models import Outcome

logger = logging.getLogger(__name__)


def compute_strategy_stats(
    db: Session,
    strategy_id: Optional[str] = None,
    days_back: int = 90,
    min_outcomes: int = 5,
) -> dict:
    """
    Compute performance statistics for one or all strategies.

    Returns dict with strategies list, overall stats, and timestamp.
    """
    cutoff = date.today() - timedelta(days=days_back)

    query = db.query(Outcome).filter(Outcome.entry_date >= cutoff)
    if strategy_id:
        query = query.filter(Outcome.strategy_id == strategy_id)

    outcomes = query.all()

    # Group by strategy
    by_strategy = {}
    for o in outcomes:
        by_strategy.setdefault(o.strategy_id, []).append(o)

    strategies = []
    for sid, group in by_strategy.items():
        stats = _compute_group_stats(sid, group, min_outcomes)
        strategies.append(stats)

    # Sort by expectancy (highest first), insufficient data last
    strategies.sort(key=lambda s: (s["confidence"] != "INSUFFICIENT", s["expectancy"] or 0), reverse=True)

    overall = _compute_group_stats("overall", outcomes, min_outcomes) if outcomes else _empty_stats("overall")

    return {
        "strategies": strategies,
        "overall": overall,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _compute_group_stats(group_id: str, outcomes: list, min_outcomes: int) -> dict:
    """Compute stats for a group of outcomes."""
    total = len(outcomes)
    complete = [o for o in outcomes if o.status == "complete"]
    tracked = [o for o in outcomes if o.status in ("complete", "partial")]

    # Win/loss based on R-multiple
    with_r = [o for o in tracked if o.theoretical_r_multiple is not None]
    winners = [o for o in with_r if o.theoretical_r_multiple > 0]
    losers = [o for o in with_r if o.theoretical_r_multiple < 0]
    open_trades = [o for o in with_r if o.theoretical_r_multiple == 0]

    win_rate = len(winners) / len(with_r) if with_r else None
    loss_rate = len(losers) / len(with_r) if with_r else None

    r_values = [o.theoretical_r_multiple for o in with_r]
    avg_r = sum(r_values) / len(r_values) if r_values else None
    median_r = _median(r_values) if r_values else None
    best_r = max(r_values) if r_values else None
    worst_r = min(r_values) if r_values else None

    # Expectancy = (win_rate * avg_win_R) + (loss_rate * avg_loss_R)
    avg_win_r = sum(o.theoretical_r_multiple for o in winners) / len(winners) if winners else 0
    avg_loss_r = sum(o.theoretical_r_multiple for o in losers) / len(losers) if losers else 0
    expectancy = None
    if win_rate is not None and loss_rate is not None:
        expectancy = round(win_rate * avg_win_r + loss_rate * avg_loss_r, 3)

    # Average returns at each milestone
    avg_returns = {}
    for day in [1, 3, 5, 10, 20]:
        field = f"price_day_{day}"
        returns = []
        for o in tracked:
            price = getattr(o, field, None)
            if price is not None and o.entry_price > 0:
                returns.append((price - o.entry_price) / o.entry_price * 100)
        avg_returns[f"avg_return_day_{day}"] = round(sum(returns) / len(returns), 2) if returns else None

    # MFE/MAE stats
    mfe_vals = [o.max_favorable_pct for o in tracked if o.max_favorable_pct is not None]
    mae_vals = [o.max_adverse_pct for o in tracked if o.max_adverse_pct is not None]
    mfe_days = [o.max_favorable_day for o in tracked if o.max_favorable_day is not None]
    mae_days = [o.max_adverse_day for o in tracked if o.max_adverse_day is not None]

    avg_mfe = round(sum(mfe_vals) / len(mfe_vals), 2) if mfe_vals else None
    avg_mae = round(sum(mae_vals) / len(mae_vals), 2) if mae_vals else None
    mfe_mae_ratio = round(avg_mfe / avg_mae, 2) if avg_mfe and avg_mae and avg_mae > 0 else None

    # Regime breakdown
    regime_stats = {}
    for regime in ["RISK_ON", "RISK_OFF", "ROTATION"]:
        regime_outcomes = [o for o in with_r if o.regime_at_scan == regime]
        if regime_outcomes:
            regime_winners = [o for o in regime_outcomes if o.theoretical_r_multiple > 0]
            regime_stats[f"win_rate_{regime.lower()}"] = round(len(regime_winners) / len(regime_outcomes), 3)
        else:
            regime_stats[f"win_rate_{regime.lower()}"] = None

    # Confidence level
    n = len(with_r)
    if n >= 30:
        confidence = "HIGH"
    elif n >= 15:
        confidence = "MODERATE"
    elif n >= min_outcomes:
        confidence = "LOW"
    else:
        confidence = "INSUFFICIENT"

    # Period
    dates = [o.entry_date for o in outcomes if o.entry_date]
    period_start = min(dates).isoformat() if dates else None
    period_end = max(dates).isoformat() if dates else None

    result = {
        "strategy_id": group_id,
        "total_scans": total,
        "tracked_outcomes": len(tracked),
        "complete_outcomes": len(complete),
        "win_rate": round(win_rate, 3) if win_rate is not None else None,
        "loss_rate": round(loss_rate, 3) if loss_rate is not None else None,
        "open_rate": round(len(open_trades) / len(with_r), 3) if with_r else None,
        "avg_r_multiple": round(avg_r, 3) if avg_r is not None else None,
        "median_r_multiple": round(median_r, 3) if median_r is not None else None,
        "best_r": round(best_r, 2) if best_r is not None else None,
        "worst_r": round(worst_r, 2) if worst_r is not None else None,
        "expectancy": expectancy,
        **avg_returns,
        "avg_mfe_pct": avg_mfe,
        "avg_mae_pct": avg_mae,
        "mfe_mae_ratio": mfe_mae_ratio,
        "avg_mfe_day": round(sum(mfe_days) / len(mfe_days), 1) if mfe_days else None,
        "avg_mae_day": round(sum(mae_days) / len(mae_days), 1) if mae_days else None,
        **regime_stats,
        "confidence": confidence,
        "period_start": period_start,
        "period_end": period_end,
    }

    return result


def _empty_stats(group_id: str) -> dict:
    """Return empty stats dict."""
    return {
        "strategy_id": group_id,
        "total_scans": 0, "tracked_outcomes": 0, "complete_outcomes": 0,
        "win_rate": None, "loss_rate": None, "open_rate": None,
        "avg_r_multiple": None, "median_r_multiple": None,
        "best_r": None, "worst_r": None, "expectancy": None,
        "avg_return_day_1": None, "avg_return_day_3": None,
        "avg_return_day_5": None, "avg_return_day_10": None, "avg_return_day_20": None,
        "avg_mfe_pct": None, "avg_mae_pct": None, "mfe_mae_ratio": None,
        "avg_mfe_day": None, "avg_mae_day": None,
        "win_rate_risk_on": None, "win_rate_risk_off": None, "win_rate_rotation": None,
        "confidence": "INSUFFICIENT", "period_start": None, "period_end": None,
    }


def compute_ticker_outcomes(db: Session, ticker: str) -> dict:
    """All outcomes for a specific ticker across strategies."""
    outcomes = db.query(Outcome).filter(Outcome.ticker == ticker).order_by(Outcome.entry_date.desc()).all()

    outcome_list = []
    for o in outcomes:
        day5_return = None
        if o.price_day_5 is not None and o.entry_price > 0:
            day5_return = round((o.price_day_5 - o.entry_price) / o.entry_price * 100, 2)

        outcome_list.append({
            "id": o.id,
            "entry_date": o.entry_date.isoformat() if o.entry_date else None,
            "strategy_id": o.strategy_id,
            "entry_price": o.entry_price,
            "price_day_5": o.price_day_5,
            "day5_return_pct": day5_return,
            "theoretical_r_multiple": o.theoretical_r_multiple,
            "status": o.status,
        })

    avg_day5 = None
    day5_returns = [o["day5_return_pct"] for o in outcome_list if o["day5_return_pct"] is not None]
    if day5_returns:
        avg_day5 = round(sum(day5_returns) / len(day5_returns), 2)

    return {
        "ticker": ticker,
        "times_scanned": len(outcomes),
        "avg_return_day_5": avg_day5,
        "outcomes": outcome_list,
    }


def compute_edge_report(db: Session, days_back: int = 90) -> dict:
    """
    Executive summary: does the system have edge?

    Returns system expectancy, win rate, best/worst strategy, regime impact, verdict.
    """
    stats = compute_strategy_stats(db, days_back=days_back)
    overall = stats["overall"]

    # Find best/worst strategy by expectancy
    valid_strategies = [s for s in stats["strategies"] if s["expectancy"] is not None]
    best = max(valid_strategies, key=lambda s: s["expectancy"]) if valid_strategies else None
    worst = min(valid_strategies, key=lambda s: s["expectancy"]) if valid_strategies else None

    # Regime impact
    regime_impact = {}
    cutoff = date.today() - timedelta(days=days_back)
    outcomes = db.query(Outcome).filter(
        Outcome.entry_date >= cutoff,
        Outcome.theoretical_r_multiple.isnot(None),
    ).all()

    for regime in ["RISK_ON", "RISK_OFF", "ROTATION"]:
        regime_outcomes = [o for o in outcomes if o.regime_at_scan == regime]
        if regime_outcomes:
            r_vals = [o.theoretical_r_multiple for o in regime_outcomes]
            regime_impact[regime.lower()] = {
                "count": len(regime_outcomes),
                "expectancy": round(sum(r_vals) / len(r_vals), 3),
            }

    # Recommendation based on regime data
    if regime_impact:
        best_regime = max(regime_impact.items(), key=lambda x: x[1]["expectancy"])
        regime_impact["recommendation"] = f"Best edge in {best_regime[0].upper()} regime ({best_regime[1]['expectancy']}R)"

    # Sample size check
    total_with_r = overall.get("tracked_outcomes", 0)
    sample_adequate = total_with_r >= 30

    # Verdict
    exp = overall.get("expectancy")
    if exp is None or total_with_r < 5:
        verdict = "INSUFFICIENT_DATA"
    elif exp > 0:
        verdict = "POSITIVE_EDGE"
    else:
        verdict = "NO_EDGE"

    return {
        "system_expectancy": exp,
        "total_trades": total_with_r,
        "winners": overall.get("win_rate"),
        "losers": overall.get("loss_rate"),
        "system_win_rate": overall.get("win_rate"),
        "best_strategy": {"id": best["strategy_id"], "expectancy": best["expectancy"]} if best else None,
        "worst_strategy": {"id": worst["strategy_id"], "expectancy": worst["expectancy"]} if worst else None,
        "regime_impact": regime_impact,
        "sample_size_adequate": sample_adequate,
        "verdict": verdict,
    }


def _median(values: list) -> float:
    """Compute median of a list of numbers."""
    if not values:
        return 0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n % 2 == 0:
        return (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    return sorted_vals[n // 2]
