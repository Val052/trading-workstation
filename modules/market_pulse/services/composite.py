"""Master synthesis — combines all layers into final Market Pulse regime."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from core.services import market_data
from modules.market_pulse.services.regime import compute_regime, RATIO_PAIRS
from modules.market_pulse.services.breadth import compute_breadth
from modules.market_pulse.services.sectors import compute_sector_rankings, SECTOR_ETFS
from modules.market_pulse.services.volatility import compute_volatility_regime

logger = logging.getLogger(__name__)

# All tickers needed for intermarket + vol analysis (not S&P 500 breadth)
PULSE_TICKERS = list(set(
    # Ratio components
    [t for pair in RATIO_PAIRS.values() for t in pair]
    # Sector ETFs
    + list(SECTOR_ETFS.keys())
    # Extra tracked assets
    + ["SPY", "QQQ", "IWM", "EFA", "EEM", "FXI", "IWF", "IWD"]
    + ["TLT", "IEF", "SHY", "HYG", "LQD", "TIP"]
    + ["GLD", "SLV", "USO", "DBC", "CPER"]
    + ["UUP", "FXE", "FXY"]
    + ["BTC-USD", "ETH-USD"]
    + ["^VIX", "^VIX3M"]
))

# Weights for master regime score
W_INTERMARKET = 0.45
W_BREADTH = 0.30
W_VOLATILITY = 0.25


def compute_market_pulse(
    universe_data: Optional[dict] = None,
    force_refresh: bool = False,
) -> dict:
    """
    Run the full Market Pulse analysis.

    Fetches all required data, computes all layers, synthesizes regime.
    Optionally accepts pre-fetched universe_data for breadth.
    """
    # Fetch pulse-specific tickers (intermarket, sectors, vol)
    logger.info("Fetching Market Pulse data...")
    pulse_data = market_data.get_multiple(PULSE_TICKERS)
    logger.info(f"Loaded {len(pulse_data)} pulse tickers")

    # 1. Intermarket regime
    intermarket = compute_regime(pulse_data)

    # 2. Breadth (uses S&P 500 universe data if available)
    if universe_data and len(universe_data) > 100:
        breadth = compute_breadth(universe_data)
    else:
        # Fetch S&P 500 data for breadth (can reuse scanner's cache)
        logger.info("Fetching S&P 500 data for breadth...")
        try:
            from core.services.universe import get_sp500_tickers
            sp500 = get_sp500_tickers()
            universe_data = market_data.get_multiple(sp500)
            breadth = compute_breadth(universe_data)
        except Exception as e:
            logger.error(f"Failed to compute breadth: {e}")
            breadth = compute_breadth({})

    # 3. Sector rankings
    sectors = compute_sector_rankings(pulse_data)

    # 4. Volatility regime
    volatility = compute_volatility_regime(pulse_data)

    # Master regime score
    im_score = intermarket["regime_score"]
    br_score = breadth["breadth_score"]
    vol_score = volatility["vol_regime_score"]

    master_score = round(
        W_INTERMARKET * im_score + W_BREADTH * br_score + W_VOLATILITY * vol_score,
        3,
    )
    master_score = max(-1.0, min(1.0, master_score))

    if master_score > 0.30:
        regime = "RISK_ON"
    elif master_score < -0.30:
        regime = "RISK_OFF"
    else:
        regime = "ROTATION"

    # Generate human-readable description
    description = _generate_description(regime, master_score, intermarket, breadth, sectors, volatility)

    # Collect notable signals
    signals = _collect_signals(intermarket, breadth, sectors, volatility)

    # Simplified context for scanner integration
    scanner_context = {
        "regime": regime,
        "regime_score": master_score,
        "vix_zone": volatility["vix_zone"],
        "breadth_momentum": breadth["breadth_momentum"],
        "rotation_pattern": sectors["rotation_pattern"],
        "leaders": sectors["leaders"],
        "laggards": sectors["laggards"],
    }

    return {
        "regime": regime,
        "regime_score": master_score,
        "regime_description": description,
        "intermarket": intermarket,
        "breadth": breadth,
        "sectors": sectors,
        "volatility": volatility,
        "signals": signals,
        "scanner_context": scanner_context,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _generate_description(regime, score, intermarket, breadth, sectors, volatility) -> str:
    """Generate 1-2 sentence human-readable regime summary."""
    parts = []

    # Regime headline
    if regime == "RISK_ON":
        parts.append(f"Risk-on environment (score {score:+.2f}).")
    elif regime == "RISK_OFF":
        parts.append(f"Risk-off environment (score {score:+.2f}).")
    else:
        parts.append(f"Rotational market (score {score:+.2f}).")

    # Key detail
    vix = volatility.get("vix_level")
    if vix:
        parts.append(f"VIX at {vix} ({volatility['vix_zone'].lower()}).")

    bm = breadth.get("breadth_momentum", "STABLE")
    pct50 = breadth.get("pct_above_50dma", 0)
    if bm == "EXPANDING":
        parts.append(f"Breadth expanding ({pct50}% above 50 DMA).")
    elif bm == "CONTRACTING":
        parts.append(f"Breadth contracting ({pct50}% above 50 DMA).")

    rotation = sectors.get("rotation_pattern", "MIXED")
    if rotation != "MIXED":
        label = rotation.replace("_", " ").title()
        leaders = ", ".join(sectors.get("leaders", [])[:3])
        parts.append(f"{label} rotation — leaders: {leaders}.")

    return " ".join(parts[:3])


def _collect_signals(intermarket, breadth, sectors, volatility) -> list:
    """Collect notable signals and warnings."""
    signals = []

    # Contrarian volatility signals
    cs = volatility.get("contrarian_signal")
    if cs == "EXTREME_FEAR":
        signals.append("CONTRARIAN BULLISH: VIX extreme + backwardation (historically marks bottoms)")
    elif cs == "EXTREME_COMPLACENCY":
        signals.append("WARNING: Extreme complacency — VIX at historic lows")

    # Breadth thrust
    if breadth.get("thrust_signal"):
        signals.append("BREADTH THRUST: Zweig analog triggered — historically very bullish")

    # Term structure
    if volatility.get("term_structure") == "BACKWARDATION":
        signals.append("VIX in backwardation — elevated near-term fear")

    # Breadth extremes
    pct50 = breadth.get("pct_above_50dma", 50)
    if pct50 < 20:
        signals.append(f"OVERSOLD: Only {pct50}% of S&P 500 above 50 DMA")
    elif pct50 > 85:
        signals.append(f"OVERBOUGHT: {pct50}% of S&P 500 above 50 DMA")

    # Ratio extremes
    for name, ratio_data in intermarket.get("ratios", {}).items():
        ts = ratio_data.get("trend_score", 0)
        if abs(ts) == 2:
            direction = "strong risk-on" if ts == 2 else "strong risk-off"
            signals.append(f"{name.replace('_', ' ').title()}: {direction} (score {ts:+d})")

    # Sector rotation
    rotation = sectors.get("rotation_pattern")
    if rotation == "DEFENSIVE":
        signals.append("Defensive rotation — utilities, staples, healthcare leading")
    elif rotation == "LATE_CYCLE":
        signals.append("Late-cycle rotation — energy, materials leading while tech/financials lag")

    return signals
