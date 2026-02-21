"""Scanner service — discovers strategies, runs scans, stores results."""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from datetime import date, datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

import app.strategies as strategies_pkg
from app.strategies.base import BaseStrategy, ScanHit
from app.models import Strategy as StrategyModel, ScanResult
from app.services import market_data

logger = logging.getLogger(__name__)


def discover_strategies() -> dict[str, BaseStrategy]:
    """
    Auto-discover all BaseStrategy subclasses in app/strategies/.
    Skips the template and the base class itself.
    Returns dict mapping strategy.id -> instance.
    """
    found: dict[str, BaseStrategy] = {}

    for importer, modname, ispkg in pkgutil.iter_modules(strategies_pkg.__path__):
        if modname.startswith("_") or modname == "base":
            continue
        try:
            module = importlib.import_module(f"app.strategies.{modname}")
        except Exception as e:
            logger.error(f"Failed to import strategy module {modname}: {e}")
            continue

        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
                try:
                    instance = obj()
                    found[instance.id] = instance
                except Exception as e:
                    logger.error(f"Failed to instantiate {name}: {e}")

    return found


def sync_strategies_to_db(db: Session, strategies: dict[str, BaseStrategy]) -> None:
    """Ensure all discovered strategies exist in the DB."""
    for strat_id, strat in strategies.items():
        existing = db.query(StrategyModel).filter(StrategyModel.id == strat_id).first()
        if existing is None:
            db.add(StrategyModel(**strat.to_db_dict()))
    db.commit()


def run_scan(
    db: Session,
    strategy_ids: list[str] | None = None,
    universe: list[str] | None = None,
) -> list[dict]:
    """
    Run active strategies against the given universe.

    1. Discover strategies, filter to active + requested
    2. Fetch market data (including SPY for RS calculations)
    3. Run each strategy's scan()
    4. Persist results to scan_results table
    5. Return list of result dicts for the API
    """
    all_strategies = discover_strategies()
    sync_strategies_to_db(db, all_strategies)

    # Filter to requested or active strategies
    if strategy_ids:
        to_run = {k: v for k, v in all_strategies.items() if k in strategy_ids}
    else:
        active_in_db = {
            s.id for s in db.query(StrategyModel).filter(StrategyModel.is_active == True).all()
        }
        to_run = {k: v for k, v in all_strategies.items() if k in active_in_db}

    if not to_run:
        logger.warning("No active strategies to run")
        return []

    # Load universe from config if not provided
    if universe is None:
        import json
        from pathlib import Path
        config_path = Path(__file__).resolve().parent.parent.parent / "config" / "universe.json"
        with open(config_path) as f:
            universe = json.load(f)["tickers"]

    # Always include SPY for RS calculations
    tickers_to_fetch = list(set(universe + ["SPY"]))
    logger.info(f"Fetching data for {len(tickers_to_fetch)} tickers...")
    data = market_data.get_multiple(tickers_to_fetch)
    logger.info(f"Got data for {len(data)} tickers")

    # Run scans
    today = date.today()
    results: list[dict] = []

    for strat_id, strategy in to_run.items():
        logger.info(f"Running strategy: {strategy.name}")
        try:
            hits = strategy.scan(universe, data)
        except Exception as e:
            logger.error(f"Strategy {strat_id} failed: {e}")
            continue

        for hit in hits:
            # Persist to DB
            scan_result = ScanResult(
                scan_date=today,
                strategy_id=strat_id,
                ticker=hit.ticker,
                price_at_scan=hit.price,
                signal_data=hit.signal_data,
            )
            db.add(scan_result)
            db.flush()  # get the id

            results.append({
                "id": scan_result.id,
                "scan_date": today.isoformat(),
                "strategy_id": strat_id,
                "strategy_name": strategy.name,
                "ticker": hit.ticker,
                "price": hit.price,
                "signal_data": hit.signal_data,
                "description": strategy.describe_signal(hit.signal_data),
            })

        logger.info(f"  → {len(hits)} hits from {strategy.name}")

    db.commit()
    return results
