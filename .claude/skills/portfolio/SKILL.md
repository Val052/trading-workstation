---
name: portfolio
description: View current holdings with live P/L, stop/target alerts, and portfolio summary. Use when the user asks about their positions, portfolio, or holdings.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# /portfolio — Holdings Tracker

**Type**: User-facing command
**Usage**: `/portfolio`

## Purpose

View current holdings with live P/L, alerts on positions near stops or targets, and portfolio summary.

## Execution Flow

1. **Read positions**: Load `memory/decisions/current-positions.md`
2. **Fetch live prices**: For each active position, get current price via data-fetcher (yfinance `t.info` for latest)
3. **Calculate per position**:
   - Unrealized P/L ($): (current_price - entry_price) × shares
   - Unrealized P/L (%): (current_price / entry_price - 1) × 100
   - Distance to stop (%): (current_price - stop_loss) / current_price × 100
   - Distance to target (%): (target - current_price) / current_price × 100
   - R-multiple achieved: (current_price - entry_price) / (entry_price - stop_loss)
4. **Flag alerts**:
   - Price within 2% of stop-loss
   - Price has hit or exceeded first target
   - Position held longer than 20 trading days (potential dead money)
5. **Portfolio summary**:
   - Total portfolio value (positions + cash)
   - Total unrealized P/L ($ and %)
   - Cash remaining
   - Number of positions / max positions
   - Sector concentration breakdown
6. **Update memory**: Write latest prices back to `memory/decisions/current-positions.md`

## Output Format

```
═══════════════════════════════════════════
  PORTFOLIO OVERVIEW
  Date: [DATE]  |  Account: $XX,XXX
═══════════════════════════════════════════

POSITIONS (X of Y max)
| Ticker | Entry | Current | Shares | P/L $ | P/L % | R | Stop Dist | Target Dist | Alert |
|--------|-------|---------|--------|-------|-------|---|-----------|-------------|-------|

SUMMARY
Total Value:  $XX,XXX
Unrealized:   +$XXX (+X.X%)
Cash:         $XX,XXX (XX%)
Exposure:     XX% invested

SECTOR CONCENTRATION
[sector]: XX% (X positions)

ALERTS
⚠️ [TICKER]: Within X% of stop-loss
✅ [TICKER]: Target 1 reached (+X.X%)
⏰ [TICKER]: Held XX days — review thesis
```

## Sub-commands

- `/portfolio` — full dashboard
- `/portfolio update` — just refresh prices and update memory, no full display
