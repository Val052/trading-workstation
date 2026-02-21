---
name: technical
description: Internal technical analysis engine. Scores trend, momentum, volume, levels, and patterns on 0-10 scale. Referenced by the analyze skill.
---

# Technical Analysis — Internal Skill

**Type**: Internal (called by `/analyze`, not directly by user)
**Purpose**: Score a ticker's technical setup on a 0-10 scale

## Analysis Components

### 1. Trend Structure
- Price vs 8 EMA, 21 EMA, 50 DMA, 100 DMA, 200 DMA
- Direction of each MA (rising, flat, falling)
- MA alignment: bullish stacking (price > 8 > 21 > 50 > 200) vs bearish
- Distance from 200 DMA as % (overextended if >15% above)

### 2. Momentum
- **RSI (14)**: Overbought (>70), oversold (<30), bullish/bearish divergence
- **MACD (12/26/9)**: Signal line crossover, histogram direction and slope
- **Stochastic RSI**: Confirm overbought/oversold with momentum context

### 3. Volatility
- **Bollinger Bands (20,2)**: Price position within bands, band width (squeeze vs expansion)
- **ATR (14)**: Current ATR, ATR as % of price, ATR trend (expanding = volatility increasing)
- **Historical volatility**: 30-day realized volatility

### 4. Volume
- Current volume vs 20-day average (ratio)
- Volume on up-days vs down-days (last 10 sessions) — accumulation or distribution
- Volume trend: increasing on advances = bullish, decreasing = caution

### 5. Key Levels
- Recent swing highs and lows (10-bar and 20-bar)
- Anchored VWAP from significant pivots (if identifiable from data)
- Round numbers / psychological levels
- Pivot points (standard: H+L+C / 3, then S1/S2/R1/R2)

### 6. Pattern Recognition
- Note obvious patterns only: double bottom/top, breakout, head & shoulders, flag/pennant
- Always flag confidence level: High (clear, textbook), Medium (identifiable but imperfect), Low (possible but ambiguous)
- Do not fabricate patterns. If nothing is clear, say "no clear pattern"

## Scoring Rubric (0-10)

| Score | Meaning | Characteristics |
|-------|---------|----------------|
| 9-10 | Strong bullish | Above all rising MAs, momentum confirming, volume supporting breakout, clear uptrend |
| 7-8 | Bullish | Above key MAs, pullback to support with momentum turning up, healthy volume |
| 5-6 | Neutral | Mixed signals, range-bound, MAs flattening, no clear direction |
| 3-4 | Bearish lean | Below key MAs, momentum weakening, volume on declines |
| 1-2 | Strong bearish | Below all MAs, breakdown confirmed, high volume selling |
| 0 | No data | Insufficient data for analysis |

## Workstation Strategy Cross-Reference

Check if this ticker matched any of the workstation's automated strategies:

```python
python3 -c "
from app.database import SessionLocal
from app.models import ScanResult
db = SessionLocal()
rows = db.query(ScanResult).filter(ScanResult.ticker=='TICKER').order_by(ScanResult.created_at.desc()).limit(5).all()
for r in rows:
    print(f'{r.scan_date} | {r.strategy_id} | \${r.price_at_scan} | signal: {r.signal_data}')
if not rows: print('No scan results for this ticker')
db.close()
"
```

If the ticker appears in scan results, note:
- Which strategies triggered (EMA Pullback RS, AVWAP Bounce, Sector Rotation)
- The signal data (RS ratio, volume ratio, AVWAP level, sector rank)
- Whether it was a full hit or near-miss

This is a convergence signal — scanner + analyst agreement strengthens the thesis.

## Output Format

Return a structured assessment:
```
TECHNICAL SCORE: X.X / 10

Trend: [Bullish/Neutral/Bearish] — [one-line summary]
Momentum: [summary with RSI, MACD values]
Volume: [summary with ratio and accumulation/distribution read]
Key Levels: Support $XXX, Resistance $XXX, Stop suggestion $XXX
Pattern: [if any, with confidence level]
Strategy Match: [workstation scan results, if any]
```
