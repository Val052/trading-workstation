---
name: data-fetcher
description: Internal data acquisition skill with MCP/yfinance/web failover. Referenced by analyze, portfolio, outlook, and other skills. Not user-invocable.
---

# Data Fetcher — Data Acquisition with Failover

**Type**: Internal skill (called by other skills, not directly by user)
**Purpose**: Retrieve financial data for a given ticker with a strict failover chain

## Data Retrieval Protocol

### Priority 1: MCP Financial Tools

When the MCP financial-data server is configured (see `.claude/mcp.json`), use these tools:

| Tool | Returns | Use For |
|------|---------|---------|
| `get_quote` | Current price, volume, 52-week range, market cap, avg volume | Price context |
| `get_financial_ratios` | P/E, P/B, P/S, EV/EBITDA, ROE, ROA, ROIC, margins, debt ratios | Valuation + quality |
| `get_technical_analysis` | RSI, MACD, Bollinger Bands, moving averages, ADX | Technical scoring |
| `get_analyst_data` | Consensus rating, price targets, number of analysts, recent changes | Sentiment |
| `get_financial_statements` | Income statement, balance sheet, cash flow (quarterly + annual) | Fundamental deep dive |
| `get_earnings` | Recent and upcoming earnings, EPS estimates, surprise history | Catalysts |
| `get_news` | Recent news headlines and summaries | Sentiment |

**If any MCP tool call fails**, fall back to Priority 2 for that specific data point. Do not abort the entire analysis.

### Priority 2: yfinance (Python)

Use direct Python calls. yfinance data is 15-20 minutes delayed — always note this.

```python
# Price data + technicals
python3 -c "
import yfinance as yf
import json
t = yf.Ticker('TICKER')
info = t.info
print(json.dumps({
    'price': info.get('currentPrice') or info.get('regularMarketPrice'),
    'previous_close': info.get('previousClose'),
    'open': info.get('open') or info.get('regularMarketOpen'),
    'day_high': info.get('dayHigh') or info.get('regularMarketDayHigh'),
    'day_low': info.get('dayLow') or info.get('regularMarketDayLow'),
    'volume': info.get('volume') or info.get('regularMarketVolume'),
    'avg_volume': info.get('averageVolume'),
    'market_cap': info.get('marketCap'),
    'pe_trailing': info.get('trailingPE'),
    'pe_forward': info.get('forwardPE'),
    'peg': info.get('pegRatio'),
    'pb': info.get('priceToBook'),
    'ps': info.get('priceToSalesTrailing12Months'),
    'ev_ebitda': info.get('enterpriseToEbitda'),
    'dividend_yield': info.get('dividendYield'),
    'beta': info.get('beta'),
    'fifty_two_week_high': info.get('fiftyTwoWeekHigh'),
    'fifty_two_week_low': info.get('fiftyTwoWeekLow'),
    'fifty_day_avg': info.get('fiftyDayAverage'),
    'two_hundred_day_avg': info.get('twoHundredDayAverage'),
    'profit_margin': info.get('profitMargins'),
    'operating_margin': info.get('operatingMargins'),
    'gross_margin': info.get('grossMargins'),
    'roe': info.get('returnOnEquity'),
    'roa': info.get('returnOnAssets'),
    'debt_to_equity': info.get('debtToEquity'),
    'current_ratio': info.get('currentRatio'),
    'revenue_growth': info.get('revenueGrowth'),
    'earnings_growth': info.get('earningsGrowth'),
    'free_cash_flow': info.get('freeCashflow'),
    'total_revenue': info.get('totalRevenue'),
    'sector': info.get('sector'),
    'industry': info.get('industry'),
    'name': info.get('longName') or info.get('shortName'),
    'analyst_target': info.get('targetMeanPrice'),
    'analyst_high': info.get('targetHighPrice'),
    'analyst_low': info.get('targetLowPrice'),
    'recommendation': info.get('recommendationKey'),
    'num_analysts': info.get('numberOfAnalystOpinions'),
}, indent=2))
"

# Historical OHLCV for technical analysis
python3 -c "
import yfinance as yf
df = yf.download('TICKER', period='1y', progress=False, auto_adjust=True)
if hasattr(df.columns, 'levels'):
    df.columns = df.columns.get_level_values(0)
print(df.tail(20).to_string())
print(f'--- {len(df)} total bars ---')
"

# Financial statements
python3 -c "
import yfinance as yf
t = yf.Ticker('TICKER')
print('=== INCOME STATEMENT (Annual) ===')
print(t.financials.to_string() if t.financials is not None else 'N/A')
print()
print('=== BALANCE SHEET ===')
print(t.balance_sheet.to_string() if t.balance_sheet is not None else 'N/A')
print()
print('=== CASH FLOW ===')
print(t.cashflow.to_string() if t.cashflow is not None else 'N/A')
"

# Earnings history
python3 -c "
import yfinance as yf
t = yf.Ticker('TICKER')
try:
    ed = t.earnings_dates
    if ed is not None: print(ed.head(8).to_string())
    else: print('No earnings dates')
except: print('Earnings dates unavailable')
"
```

### Priority 3: Web Search

Use web search for qualitative data not available from structured sources:
- Recent news and catalysts
- Regulatory developments
- Management commentary from earnings calls
- Industry trends and competitive dynamics

## Rules

1. **Always timestamp data.** Note when each data point was retrieved and from which source.
2. **Mark missing data explicitly.** Use `[DATA UNAVAILABLE]` — never estimate or interpolate.
3. **Note delays.** yfinance data is 15-20 min delayed. MCP data latency depends on provider.
4. **Cache awareness.** The workstation caches yfinance OHLCV daily in SQLite. For intraday freshness, use `t.info` (not the cached DataFrames).
5. **Handle failures gracefully.** If yfinance throws an exception for a ticker, report it and continue with whatever data was obtained.
6. **Respect rate limits.** Don't make more than 3 concurrent yfinance requests. The `market_data.py` service handles this for batch operations.

## Cross-Reference with Workstation

Before fetching fresh data, check if the ticker has cached price data in the workstation:

```python
python3 -c "
from app.services.market_data import get_price_data
df = get_price_data('TICKER')
if df is not None:
    print(f'Cached data: {len(df)} bars, latest close: \${df[\"Close\"].iloc[-1]:.2f}')
    print(f'Date range: {df.index[0].date()} to {df.index[-1].date()}')
else:
    print('No cached data')
"
```

This avoids redundant downloads when the scanner has already fetched today's data.
