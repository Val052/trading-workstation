---
name: screen
description: Stock screener with presets (value, growth, momentum, dividend, quality). Bridges terminal with the web app scanner. Use when the user wants to screen or find stocks matching criteria.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebSearch, WebFetch
---

# /screen — Stock Screener Bridge

**Type**: User-facing command
**Usage**: `/screen [market] [preset]`

## Purpose

Bridge between the terminal and the web app's automated screener, plus custom screening via MCP/web search.

## Execution Flow

1. **Check if preset maps to existing strategy**:
   - `momentum` → EMA Pullback RS strategy
   - Custom screens → direct yfinance/MCP queries
2. **Run the appropriate scan**
3. **Present results in a ranked table**
4. **Offer `/analyze` on any result**

## Presets

### `momentum` — Relative Strength Momentum
Maps to the workstation's EMA Pullback RS + Sector Rotation strategies:
```python
python3 -c "
from app.database import init_db, SessionLocal
from app.services.scanner import run_scan
init_db()
db = SessionLocal()
output = run_scan(db, strategy_ids=['ema_pullback_rs', 'sector_rotation'])
results = output['results']
near_misses = output['near_misses']
print(f'Hits: {len(results)}, Near-misses: {len(near_misses)}')
for r in results[:15]:
    print(f'{r[\"ticker\"]:6s} {r[\"strategy_id\"]:20s} \${r[\"price\"]:>8.2f}  {r[\"description\"][:60]}')
if near_misses:
    print('\\n--- Near Misses ---')
    for r in near_misses[:10]:
        print(f'{r[\"ticker\"]:6s} {r[\"strategy_id\"]:20s} \${r[\"price\"]:>8.2f}  failed: {r[\"failed_filter\"]}')
db.close()
"
```

### `value` — Deep Value
Screen for: Low P/E (<15), low P/B (<1.5), positive FCF, debt-to-equity <1.0
Use web search or MCP to find candidates, then verify with yfinance data.

### `growth` — High Growth
Screen for: Revenue growth >20% YoY, earnings acceleration, expanding margins, above 200 DMA.

### `dividend` — Dividend Income
Screen for: Yield >2%, payout ratio <60%, 5+ years of dividend growth, positive FCF.

### `quality` — Quality Compounders
Screen for: ROIC >15%, debt-to-equity <0.5, Piotroski F-Score >7, above 200 DMA, market cap >$10B.

## Custom Screens

If the user specifies criteria not matching a preset:
- Parse the criteria
- Use web search to find stock screener results matching those criteria
- Verify top candidates with yfinance data
- Present verified results

## Output Format

```
═══════════════════════════════════════════
  SCREEN: [PRESET] — [MARKET]
  Date: [DATE]  |  Universe: [count] stocks
═══════════════════════════════════════════

RESULTS (sorted by relevance)
| # | Ticker | Price | Key Metric 1 | Key Metric 2 | Signal |
|---|--------|-------|-------------|-------------|--------|
| 1 | XXX | $XXX | ... | ... | ... |
...

NEAR MISSES (close but didn't pass all filters)
| Ticker | Price | Failed | Notes |
|--------|-------|--------|-------|
...

Run /analyze [TICKER] for deep-dive on any result.
```
