# Trading Terminal

A modular, local-first trading terminal combining automated scanning, portfolio intelligence, and AI-powered research. Built as a platform with independent functional modules sharing a common data layer, instrument universe, and UI shell.

## Architecture

**Platform + Modules** (FastAPI/SQLite on `http://127.0.0.1:8000`)
- Platform layer (`core/`): database, shared services (market data, instrument registry, event log, cache), UI shell
- Module system (`modules/`): each module registers routes, models, and UI panels
- Current modules: Scanner, Portfolio
- Database: `data/terminal.db` (SQLite, gitignored)
- Run: `make run` or `python3 run.py`

**Skills Layer** (Claude Code terminal)
- Deep-dive research and analysis on individual securities
- Macro views, portfolio management, reporting
- Memory system for persistent context across sessions
- Skills live in `.claude/skills/` — plain markdown, no code files

**Scanner surfaces candidates → Skills investigate them → Portfolio tracks holdings → Event log connects everything.**

## File Structure

```
core/                          # Platform layer
  app.py                       # FastAPI app factory, module discovery
  database.py                  # SQLite engine, SessionLocal, get_db
  models/                      # Platform models (Base, Instrument, Event, PriceCache)
  services/                    # Shared services (market_data, universe, instrument_registry, event_log, cache)
  ui/
    shell.html                 # Main layout: sidebar + content area
    static/                    # shell.js, shell.css
    module_panels/             # Per-module HTML/JS panels

modules/                       # Functional modules
  base.py                      # BaseModule ABC
  scanner/                     # Scanner module
    models.py                  # Strategy, ScanResult, Candidate, Outcome, AccountConfig
    routers/                   # API routes under /api/scanner/
    services/                  # scanner.py, risk_calculator.py
    strategies/                # Pluggable strategy modules (auto-discovered)
  portfolio/                   # Portfolio module
    models.py                  # PortfolioHolding, PortfolioSnapshot
    routers/                   # API routes under /api/portfolio/
    services/                  # enrichment.py

config/settings.yaml           # Platform + module config
memory/                        # Skills layer persistent memory
.claude/skills/                # Skill definitions
```

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
2. **Maximum 2% portfolio risk per trade.** Position size = (account_size x 0.02) / risk_per_share.
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

Composite -> Recommendation: Strong Buy (8.5+), Buy (7.0-8.4), Hold (5.0-6.9), Sell (3.0-4.9), Strong Sell (<3.0)

## Integration Queries

```python
# Check if ticker appeared in recent scans
python3 -c "
from core.database import SessionLocal
from modules.scanner.models import ScanResult
db = SessionLocal()
rows = db.query(ScanResult).filter(ScanResult.ticker=='AAPL').order_by(ScanResult.created_at.desc()).limit(5).all()
for r in rows:
    print(f'{r.scan_date} {r.strategy_id} @ \${r.price_at_scan} signal={r.signal_data}')
db.close()
"

# Read account config
python3 -c "
from core.database import SessionLocal
from modules.scanner.models import AccountConfig
db = SessionLocal()
a = db.query(AccountConfig).order_by(AccountConfig.id.desc()).first()
if a: print(f'Size: {a.account_size}, Risk: {a.risk_per_trade}, Max Pos: {a.max_positions}')
else: print('No account config — using defaults: 10000, 0.005, 5')
db.close()
"

# Query event log
python3 -c "
from core.database import SessionLocal
from core.models.events import Event
db = SessionLocal()
events = db.query(Event).order_by(Event.timestamp.desc()).limit(10).all()
for e in events:
    print(f'{e.timestamp} {e.module}/{e.event_type} instrument={e.instrument_id}')
db.close()
"
```

## Technical Notes

- Python 3.9 on macOS — use `Optional[X]` not `X | None` in Pydantic models and FastAPI params
- `from __future__ import annotations` is safe in non-Pydantic files
- yfinance single-ticker downloads return MultiIndex — flatten with `.get_level_values(0)`
- Platform uses `core/` (not `platform/`) to avoid shadowing Python's stdlib `platform` module
- Old `app/` directory kept for reference — will be removed once migration is fully verified
