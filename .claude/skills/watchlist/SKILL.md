---
name: watchlist
description: Manage watchlist of tickers with target entry prices. Track prices, alert when targets reached, add/remove tickers. Use when the user wants to manage their watchlist.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# /watchlist — Target Tracking

**Type**: User-facing command
**Usage**: `/watchlist [sub-command]`

## Purpose

Manage a watchlist of tickers with target entry prices. Track them, alert when targets are reached, and connect to `/analyze` for fresh assessments.

## Sub-commands

### `/watchlist` (no args) — Show All
1. Read `memory/decisions/current-positions.md` (watchlist section)
2. Fetch current prices for all watched tickers
3. Display: ticker, target entry, current price, distance to target (%), last analysis date, score at last analysis
4. Flag tickers that have reached or passed their target entry zone
5. Offer `/analyze` on any flagged ticker

### `/watchlist add [TICKER] [TARGET_PRICE]` — Add
1. Validate the ticker exists (quick yfinance check)
2. Fetch current price
3. Add row to watchlist table in `memory/decisions/current-positions.md`
4. Note if the ticker has been previously analyzed (check `analysis-log.md`)

### `/watchlist remove [TICKER]` — Remove
1. Remove the ticker's row from the watchlist table in `memory/decisions/current-positions.md`
2. Confirm removal

### `/watchlist check` — Quick Price Check
1. Fetch all prices without the full display
2. Only show tickers where price is within 3% of target entry
3. These are actionable — suggest running `/analyze` on them

## Output Format

### Full Watchlist
```
═══════════════════════════════════════════
  WATCHLIST — [COUNT] tickers tracked
  Date: [DATE]
═══════════════════════════════════════════

| Ticker | Target | Current | Dist % | Last Score | Last Analyzed | Status |
|--------|--------|---------|--------|------------|---------------|--------|
| NVDA | $180.00 | $189.82 | -5.2% | — | — | Watching |
| AAPL | $250.00 | $264.58 | -5.5% | — | — | Watching |

🎯 ALERTS (within 3% of target)
  [TICKER] at $XXX — target $XXX (X.X% away). Run /analyze [TICKER]?

Last updated: [timestamp]
```

### Add Confirmation
```
Added [TICKER] to watchlist
  Target entry: $XXX.XX
  Current price: $XXX.XX (X.X% away)
  Previous analysis: [date and score, or "none"]
```

## Memory Integration

The watchlist lives in `memory/decisions/current-positions.md` under the `## Watchlist` section. Format:

```markdown
## Watchlist
| Ticker | Target Entry | Last Price | Last Score | Last Analyzed | Notes |
|--------|-------------|------------|------------|---------------|-------|
| NVDA | 180.00 | 189.82 | — | — | Near-miss on EMA pullback (volume) |
```

When updating, preserve the table structure and only modify relevant rows.
