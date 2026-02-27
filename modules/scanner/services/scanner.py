"""Scanner service — discovers strategies, runs scans, stores results."""

from __future__ import annotations

import importlib
import inspect
import logging
import pkgutil
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

import modules.scanner.strategies as strategies_pkg
from modules.scanner.strategies.base import BaseStrategy, ScanHit
from modules.scanner.models import Strategy as StrategyModel, ScanResult
from core.services import market_data
from core.services.event_log import log_event

logger = logging.getLogger(__name__)


def discover_strategies() -> dict:
    """
    Auto-discover all BaseStrategy subclasses in modules/scanner/strategies/.
    Skips the template and the base class itself.
    Returns dict mapping strategy.id -> instance.
    """
    found = {}

    for importer, modname, ispkg in pkgutil.iter_modules(strategies_pkg.__path__):
        if modname.startswith("_") or modname == "base":
            continue
        try:
            module = importlib.import_module(f"modules.scanner.strategies.{modname}")
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


def sync_strategies_to_db(db: Session, strategies: dict) -> None:
    """Ensure all discovered strategies exist in the DB."""
    for strat_id, strat in strategies.items():
        existing = db.query(StrategyModel).filter(StrategyModel.id == strat_id).first()
        if existing is None:
            db.add(StrategyModel(**strat.to_db_dict()))
    db.commit()


def _collect_extra_tickers(strategies: dict) -> list:
    """
    Some strategies (e.g. sector rotation) need tickers beyond the main universe.
    Collect them here so we fetch all data in one pass.
    """
    extra = []
    # Sector rotation needs sector ETF data + sector stock data
    if "sector_rotation" in strategies:
        from core.services.universe import SECTOR_ETFS
        from modules.scanner.strategies.sector_rotation import SECTOR_STOCKS
        extra.extend(SECTOR_ETFS.keys())
        for stocks in SECTOR_STOCKS.values():
            extra.extend(stocks)
    return extra


def run_scan(
    db: Session,
    strategy_ids: Optional[list] = None,
    universe: Optional[list] = None,
) -> dict:
    """
    Run active strategies against the given universe.

    Returns dict with 'results' (full hits) and 'near_misses'.
    Both lists contain result dicts. Near misses are NOT stored in DB.
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
        return {"results": [], "near_misses": []}

    # Load universe from config if not provided
    if universe is None:
        from core.services.universe import get_universe
        universe = get_universe()

    # Collect all tickers we need: universe + SPY + strategy extras
    extra = _collect_extra_tickers(to_run)
    tickers_to_fetch = list(set(universe + ["SPY"] + extra))
    logger.info(f"Fetching data for {len(tickers_to_fetch)} tickers...")
    data = market_data.get_multiple(tickers_to_fetch)
    logger.info(f"Got data for {len(data)} tickers")

    # Run scans
    today = date.today()
    results = []
    near_misses = []

    for strat_id, strategy in to_run.items():
        logger.info(f"Running strategy: {strategy.name}")
        try:
            hits = strategy.scan(universe, data)
        except Exception as e:
            logger.error(f"Strategy {strat_id} failed: {e}")
            continue

        full_count = 0
        near_count = 0

        for hit in hits:
            result_dict = {
                "scan_date": today.isoformat(),
                "strategy_id": strat_id,
                "strategy_name": strategy.name,
                "ticker": hit.ticker,
                "price": hit.price,
                "signal_data": hit.signal_data,
                "description": strategy.describe_signal(hit.signal_data),
                "near_miss": hit.near_miss,
                "failed_filter": hit.failed_filter,
            }

            if hit.near_miss:
                near_misses.append(result_dict)
                near_count += 1
            else:
                # Persist full hits to DB
                scan_result = ScanResult(
                    scan_date=today,
                    strategy_id=strat_id,
                    ticker=hit.ticker,
                    price_at_scan=hit.price,
                    signal_data=hit.signal_data,
                )
                db.add(scan_result)
                db.flush()
                result_dict["id"] = scan_result.id
                results.append(result_dict)
                full_count += 1

        logger.info(f"  -> {full_count} hits, {near_count} near-misses from {strategy.name}")

    db.commit()

    # Log scan event
    log_event(
        module="scanner",
        event_type="scan_run",
        data={
            "strategies": list(to_run.keys()),
            "universe_size": len(universe),
            "results_count": len(results),
            "near_miss_count": len(near_misses),
        },
    )

    return {"results": results, "near_misses": near_misses}
