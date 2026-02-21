---
name: outlook
description: Macro market views across equities, crypto, commodities, forex, and volatility. Fetches current data and compares to stored views. Use when the user asks about market conditions or macro outlook.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, WebSearch, WebFetch
---

# /outlook — Macro Market Views

**Type**: User-facing command
**Usage**: `/outlook`

## Purpose

Present current macro stance across markets, surface new data that might challenge existing views, and offer to update the outlook.

## Execution Flow

1. **Read current views**: Load `memory/economic-views/market-outlook.md`, `sector-views.md`, `macro-indicators.md`
2. **Fetch current data** via data-fetcher:
   - Major indices: SPY, QQQ, IWM (S&P 500, Nasdaq 100, Russell 2000)
   - Volatility: VIX (via ^VIX)
   - Bonds: TLT or ^TNX (10-year yield)
   - Dollar: UUP or DXY
   - Commodities: GLD (gold), USO (oil)
   - Crypto: BTC-USD, ETH-USD
   - International: EFA (developed), EEM (emerging markets)
   - Sector ETFs: XLK, XLF, XLE, XLV, XLY, XLP, XLI, XLU, XLRE, XLB, XLC
3. **Present dashboard**:
   - Current prices and recent performance (1d, 5d, 1m, 3m)
   - Compare to stored views — highlight where data contradicts the thesis
   - Sector rotation: rank sectors by 20-day RS, compare to stored rankings
4. **Surface contradictions**: If the data tells a different story than the stored views, call it out explicitly
5. **Offer update**: Ask if any views should be changed based on new data
6. **If yes**: Update `market-outlook.md`, `sector-views.md`, and `macro-indicators.md`

## Data Fetching

```python
# Quick multi-ticker price check
python3 -c "
import yfinance as yf
tickers = ['SPY','QQQ','IWM','^VIX','TLT','GLD','USO','BTC-USD','ETH-USD','UUP','EFA','EEM']
for t in tickers:
    try:
        info = yf.Ticker(t).info
        price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
        change = info.get('regularMarketChangePercent', 0)
        print(f'{t:12s} \${price:>10.2f}  {change:+.2f}%')
    except: print(f'{t:12s} [error]')
"
```

## Output Format

```
═══════════════════════════════════════════
  MARKET OUTLOOK
  Date: [DATE]
═══════════════════════════════════════════

MAJOR MARKETS
| Market | Price | 1D | 5D | 1M | View | Status |
|--------|-------|-----|-----|-----|------|--------|
| S&P 500 | $XXX | +X% | +X% | +X% | [view] | [confirming/challenging] |
...

SECTOR ROTATION (20-day RS ranking)
| Rank | Sector | ETF | RS | Prev Rank | Trend |
|------|--------|-----|----|-----------|-------|
...

VOLATILITY & RISK
VIX: XX.XX — [low/normal/elevated/extreme]
Yield Curve (2Y-10Y): XXXbps — [normal/flat/inverted]

CONTRADICTIONS TO CURRENT VIEWS
[list any data points that challenge stored outlook]

Update views? [prompt for confirmation]
```

## Markets Covered
- US Equities: S&P 500 (SPY), Nasdaq 100 (QQQ), Russell 2000 (IWM)
- International: Developed (EFA), Emerging Markets (EEM)
- Crypto: Bitcoin (BTC-USD), Ethereum (ETH-USD)
- Fixed Income: 20Y Treasury (TLT), 10Y Yield (^TNX)
- Commodities: Gold (GLD), Oil (USO)
- Forex: US Dollar Index (UUP/DXY)
- Volatility: VIX (^VIX)
