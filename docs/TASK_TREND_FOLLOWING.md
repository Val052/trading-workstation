# Task: Add Trend Following Strategy + Multi-Timeframe Scoring

## Context

This adds two capabilities to the existing Scanner module:

1. **Donchian Channel Trend Following strategy** — philosophically different from existing mean-reversion/pullback strategies. Accepts lower win rates (35-45%) for asymmetric payoffs by letting winners run.

2. **Weekly timeframe scoring** added to ALL scan results — enriches every ScanHit with multi-timeframe alignment data.

The strategy architecture uses pluggable `BaseStrategy` subclasses auto-discovered in the strategies directory. See `base.py` for the interface.

## Files to Create

```
modules/scanner/strategies/
  trend_following.py          # New strategy module

modules/scanner/services/
  weekly_enrichment.py        # Weekly timeframe scoring service
```

## 1. Trend Following Strategy

### Strategy Definition

```python
class TrendFollowingStrategy(BaseStrategy):
    id = "trend_following"
    name = "Donchian Trend Following"
    description = (
        "Donchian channel breakout with ATR trailing stop. "
        "Captures trending stocks making new highs with controlled risk. "
        "Accepts lower win rate for asymmetric reward."
    )
    source = "Donchian/Turtle Traders methodology, adapted for equity swing trading"
    parameters = {
        "donchian_period": 50,          # N-day high/low channel
        "donchian_entry_period": 20,    # Shorter channel for entry trigger
        "atr_period": 14,              # ATR calculation period
        "atr_stop_multiple": 2.5,      # Trailing stop = entry - N * ATR
        "min_atr_pct": 0.01,           # Min ATR as % of price
        "max_atr_pct": 0.06,           # Max ATR as % of price
        "volume_confirm_ratio": 1.2,   # Breakout volume > N * 20d avg
        "min_rs_ratio": 1.0,           # Must outperform SPY
        "lookback_days": 60,
        "require_consolidation": True,
    }
    references = [
        "Curtis Faith - Way of the Turtle",
        "Michael Covel - Trend Following",
        "JC Parets - intermarket trend analysis",
    ]
```

### Scan Logic

**Step 1: Compute Donchian Channels**
```python
upper_channel = df["High"].rolling(donchian_period).max()
lower_channel = df["Low"].rolling(donchian_period).min()
entry_channel = df["High"].rolling(donchian_entry_period).max()
```

**Step 2: Compute ATR**
```python
tr = pd.concat([
    df["High"] - df["Low"],
    (df["High"] - df["Close"].shift(1)).abs(),
    (df["Low"] - df["Close"].shift(1)).abs(),
], axis=1).max(axis=1)
atr = tr.rolling(atr_period).mean()
```

**Step 3: Entry Signal Filters (ALL must be true):**

1. **Breakout:** Close > entry_channel (shifted 1 day) — new 20-day high
2. **Not extended:** Close within 3% of entry_channel value
3. **Consolidation:** At least 5 of last 20 days had close BELOW entry_channel
4. **Volume:** Today's volume > volume_confirm_ratio * 20d average volume
5. **ATR range:** min_atr_pct < (ATR/price) < max_atr_pct
6. **Relative strength:** 20-day return > SPY 20-day return * min_rs_ratio
7. **Trend alignment:** 50 DMA > 200 DMA (golden cross)

**Step 4: Signal Data**
```python
signal_data = {
    "entry_price": current_close,
    "donchian_high_20": entry_channel_value,
    "donchian_high_50": upper_channel_value,
    "donchian_low_50": lower_channel_value,
    "atr": current_atr,
    "atr_pct": current_atr / current_close,
    "trailing_stop": current_close - (atr_stop_multiple * current_atr),
    "stop_distance_pct": (atr_stop_multiple * current_atr) / current_close,
    "volume_ratio": todays_volume / avg_volume_20d,
    "rs_vs_spy_20d": stock_return_20d / spy_return_20d,
    "consolidation_days": days_below_channel,
    "channel_width_pct": (upper_channel - lower_channel) / current_close,
    "breakout_type": "NEW_20D_HIGH" or "NEW_50D_HIGH",
}
```

**Step 5: Near-Miss Logic**
Near miss if passes all but exactly ONE of: volume confirmation, consolidation check, RS ratio (between 0.9 and 1.0).

### describe_signal Output

Format: `"New 20D High | ATR stop 4.2% below entry | Volume 1.5x average | RS vs SPY 1.12"`

## 2. Weekly Timeframe Enrichment

### `services/weekly_enrichment.py`

Enriches ANY scan result with weekly alignment data. Runs after all strategies produce hits.

```python
def enrich_with_weekly(scan_results: list, data: dict) -> list:
    """
    Add weekly_context to each result's signal_data.
    
    weekly_context = {
        "weekly_trend_score": int,     # -2 to +2
        "above_10w_ma": bool,
        "above_40w_ma": bool,
        "weekly_ma_stack": str,        # "BULLISH"/"BEARISH"/"CROSS_UP"/"CROSS_DOWN"
        "weekly_rs_trend": str,        # "IMPROVING"/"DECLINING"/"STABLE"
        "weekly_close_position": float, # 0-1 in weekly range
        "alignment_score": float,      # 0.0-1.0
        "alignment_label": str,        # "STRONG"/"MODERATE"/"WEAK"/"CONFLICTING"
    }
    """
```

**Weekly data:** Resample daily data to weekly (no extra yfinance call):
```python
def _resample_to_weekly(daily_df):
    return daily_df.resample("W-FRI").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum",
    }).dropna()
```

**Alignment score (0-4, normalized to 0-1):**
- Price above 10-week MA: +1
- Price above 40-week MA: +1
- 10-week > 40-week (weekly golden cross): +1
- Weekly RS improving: +1

**Labels:** STRONG (>=0.75), MODERATE (>=0.50), WEAK (>=0.25), CONFLICTING (<0.25)

### Scanner Integration

After strategies produce hits, before returning:
```python
from modules.scanner.services.weekly_enrichment import enrich_with_weekly
results = enrich_with_weekly(results, data)
results.sort(key=lambda r: r.get("signal_data", {}).get("weekly_context", {}).get("alignment_score", 0), reverse=True)
```

### UI Update

Add **Alignment** column to scan results table, color-coded: green=STRONG, yellow=MODERATE, orange=WEAK, red=CONFLICTING.

## Configuration

Add to `config/settings.yaml`:
```yaml
strategies:
  active:
    - ema_pullback_rs
    - avwap_bounce
    - sector_rotation
    - trend_following
  weekly_enrichment:
    enabled: true
    sort_by_alignment: true
```

## Key Behavioral Difference

Existing strategies: buy the dip in an uptrend (higher win rate, capped reward).
Trend Following: buy the breakout, ride the trend (lower win rate, uncapped reward).

This is genuine methodological diversification. In trending markets, TF captures moves pullback strategies miss. In choppy markets, pullback strategies work while TF gets stopped out. Together they smooth returns across regimes — especially with Market Pulse regime context.

## Testing Checklist

- [ ] Strategy auto-discovers in strategies list
- [ ] Scan includes trend_following results
- [ ] Signal data has all fields (donchian, ATR, stops)
- [ ] Near-miss detection works
- [ ] Trailing stop = entry - (2.5 * ATR)
- [ ] Volume filter functional
- [ ] Consolidation check counts correctly
- [ ] Weekly enrichment adds context to ALL results
- [ ] Results sort by alignment when enabled
- [ ] Risk calculator handles wider ATR stops (smaller positions expected)