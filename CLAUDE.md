# Trading Workstation

A modular, local-first trading research system combining automated strategy scanning with AI-powered deep analysis. Built for a swing trader transitioning from study to execution, with a poker player's emphasis on EV, position sizing, and process over outcome.

## Architecture

Two parallel systems sharing data:

**Web App** (FastAPI/SQLite on `http://127.0.0.1:8000`)
- Automated strategy scanners: EMA Pullback RS, AVWAP Bounce, Sector Rotation
- Broad universe scanning (S&P 500), risk calculator, watchlist, candidate tracking
- Code lives in `app/` — models, routers, services, strategies
- Database: `data/workstation.db` (SQLite)
- Run: `make run` or `python3 run.py`

**Skills Layer** (Claude Code terminal)
- Deep-dive research and analysis on individual securities
- Macro views, portfolio management, reporting
- Memory system for persistent context across sessions
- Skills live in `.claude/skills/` — plain markdown, no code files

**Scanner surfaces candidates → Skills investigate them → Memory connects everything over time.**

## Slash Commands

| Command | Description |
|---------|-------------|
| `/analyze [TICKER] [mode]` | Deep-dive research report (modes: full, quick, update) |
| `/portfolio` | View holdings, P/L, alerts on positions near stops/targets |
| `/outlook` | Macro market views across equities, crypto, commodities, forex |
| `/screen [market] [preset]` | Stock screener (presets: value, growth, momentum, dividend, quality) |
| `/watchlist` | View/manage target tracking list with price alerts |

## Risk Rules (Hard Constraints)

These are non-negotiable. Every analysis and recommendation must respect them:

1. **Never fabricate data.** If a data point is unavailable from any source, mark it `[DATA UNAVAILABLE]`. Never interpolate or estimate missing financial data.
2. **Maximum 2% portfolio risk per trade.** Position size = (account_size × 0.02) / risk_per_share.
3. **Maximum 10% portfolio allocation to a single position.**
4. **Always define stop-loss levels.** No recommendation without a concrete stop.
5. **Always show data sources and timestamps.** Every data point should be traceable.
6. **All output is research only, not execution signals.** Include disclaimer on every report.

## Memory Protocol

On every analysis or portfolio operation:

1. **Read first**: Check relevant memory files before producing output
   - `memory/decisions/current-positions.md` — existing exposure, account size
   - `memory/decisions/analysis-log.md` — prior analyses of this ticker
   - `memory/economic-views/market-outlook.md` — current macro stance
2. **Write after**: Update memory files with new findings
   - Log the analysis in `analysis-log.md`
   - Save full reports to `memory/reports/[TICKER]_[DATE].md`
   - Update watchlist or positions if warranted
3. **Never overwrite** — append to logs, update tables in-place

## Data Priority

1. **MCP tools first** — live financial data server (when configured in `.claude/mcp.json`)
2. **yfinance fallback** — `python3 -c "import yfinance as yf; ..."` (15-20 min delayed)
3. **Web search last resort** — for qualitative data (news, catalysts, analyst commentary)
4. **Never guess** — if all sources fail, say so

## Scoring Framework

The `/analyze` command uses a weighted composite system (documented in `.claude/skills/analyze/SKILL.md`):

| Component | Weight | Scale | What it measures |
|-----------|--------|-------|-----------------|
| Technical | 30% | 0-10 | Trend, momentum, volume, levels |
| Fundamental | 40% | 0-10 | Valuation, quality, growth, health |
| Sentiment | 15% | 0-5 | News, analysts, catalysts |
| Risk | 15% | 0-5 | Volatility, sizing, concentration |

Composite → Recommendation: Strong Buy (8.5+), Buy (7.0-8.4), Hold (5.0-6.9), Sell (3.0-4.9), Strong Sell (<3.0)

## Codebase Reference

Key files in the existing web app (do not modify unless explicitly needed for integration):

- `app/models.py` — SQLAlchemy models: strategies, scan_results, candidates, outcomes, account_config, price_cache
- `app/services/market_data.py` — yfinance wrapper with daily SQLite caching
- `app/services/scanner.py` — strategy discovery and scan execution
- `app/services/risk_calculator.py` — position sizing, R-multiples
- `app/services/universe.py` — S&P 500 ticker list, sector ETFs
- `app/strategies/` — pluggable strategy modules (base.py, ema_pullback_rs.py, avwap_bounce.py, sector_rotation.py)
- `config/settings.yaml` — account config, universe selection, active strategies
- `data/workstation.db` — SQLite database (gitignored)

**Integration queries** (for Skills to read scanner data):
```python
# Check if ticker appeared in recent scans
python3 -c "
from app.database import SessionLocal
from app.models import ScanResult
db = SessionLocal()
rows = db.query(ScanResult).filter(ScanResult.ticker=='AAPL').order_by(ScanResult.created_at.desc()).limit(5).all()
for r in rows:
    print(f'{r.scan_date} {r.strategy_id} @ \${r.price_at_scan} signal={r.signal_data}')
db.close()
"

# Read account config
python3 -c "
from app.database import SessionLocal
from app.models import AccountConfig
db = SessionLocal()
a = db.query(AccountConfig).order_by(AccountConfig.id.desc()).first()
if a: print(f'Size: {a.account_size}, Risk: {a.risk_per_trade}, Max Pos: {a.max_positions}')
else: print('No account config — using defaults: 10000, 0.005, 5')
db.close()
"
```
