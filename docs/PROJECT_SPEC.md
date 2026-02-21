# Trading Workstation — Project Spec

## Vision

A modular, local-first trading workstation that surfaces opportunities via pluggable strategy scanners, calculates risk/reward across multiple trade structures (stock + options), tracks outcomes over time, and builds a personal strategy playbook. Designed for a swing trader transitioning from study to execution, with a poker player's emphasis on EV, position sizing, and process over outcome.

## Core Principles

- **Local-first**: Runs on Mac, SQLite database, no cloud dependencies. Data sovereignty preserved.
- **Modular strategies**: Every strategy is a pluggable Python module. Adding a new strategy never requires touching core code.
- **Math over vibes**: All risk/reward is calculated precisely — position sizes, R-multiples, probability estimates, options Greeks.
- **Cross-referencing**: Candidates can trigger multiple strategies simultaneously. Convergence signals are surfaced.
- **Build in layers**: Each phase is independently useful. Don't build Phase 2 until Phase 1 is in daily use.

---

## Tech Stack

- **Backend**: Python 3.11+, FastAPI
- **Frontend**: Simple web UI (HTML/JS/CSS or lightweight React — keep it clean, not fancy)
- **Database**: SQLite via SQLAlchemy (easy migration to Postgres later if needed)
- **Data**: yfinance for price data + options chains. Free tier only for now.
- **Options math**: `py_vollib` or custom Black-Scholes implementation
- **Runner**: Local dev server, launched via simple command (`python run.py` or `make run`)

---

## Data Model

### Core Tables

```
strategies
  id              TEXT PRIMARY KEY (slug: "ema_pullback_rs")
  name            TEXT ("EMA Pullback with Relative Strength")
  description     TEXT (what this strategy looks for)
  source          TEXT ("RDT Wiki, Shannon AVWAP Ch.7")
  parameters      JSON (configurable thresholds, e.g. {"ema_fast": 8, "ema_slow": 21, "rs_lookback": 10})
  is_active       BOOLEAN
  created_at      DATETIME
  notes           TEXT (personal playbook notes, references, links)

scan_results
  id              INTEGER PRIMARY KEY
  scan_date       DATE
  strategy_id     TEXT FK -> strategies
  ticker          TEXT
  price_at_scan   REAL
  signal_data     JSON (strategy-specific: RS score, distance to EMA, AVWAP level, etc.)
  notes           TEXT (optional manual notes)
  created_at      DATETIME

candidates (bookmarked scan results the user wants to track)
  id              INTEGER PRIMARY KEY
  scan_result_id  INTEGER FK -> scan_results
  ticker          TEXT
  entry_price     REAL (proposed or actual)
  stop_loss       REAL
  target_1        REAL
  target_2        REAL (optional)
  risk_per_share  REAL (computed: entry - stop)
  reward_per_share REAL (computed: target - entry)
  r_multiple      REAL (computed: reward / risk)
  position_size   INTEGER (computed from account risk rules)
  trade_structure TEXT ("stock", "pcs", "naked_put", "cdc", "long_call", etc.)
  options_analysis JSON (if applicable — see Options Analysis section)
  status          TEXT ("watching", "entered", "exited", "expired")
  created_at      DATETIME

outcomes (auto-tracked price action after scan)
  id              INTEGER PRIMARY KEY
  scan_result_id  INTEGER FK -> scan_results
  ticker          TEXT
  price_day_1     REAL
  price_day_3     REAL
  price_day_5     REAL
  price_day_10    REAL
  max_favorable   REAL (best price in direction of thesis over 10 days)
  max_adverse     REAL (worst price against thesis over 10 days)
  would_have_hit_target BOOLEAN
  would_have_hit_stop   BOOLEAN
  updated_at      DATETIME

account_config
  id              INTEGER PRIMARY KEY
  account_size    REAL
  risk_per_trade  REAL (as decimal, e.g. 0.005 for 0.5%)
  max_positions   INTEGER
  updated_at      DATETIME
```

### Options Analysis JSON Structure (stored in candidates.options_analysis)

```json
{
  "underlying_price": 185.50,
  "iv_rank": 45,
  "analysis_date": "2025-02-21",
  "structures": [
    {
      "type": "stock_with_stop",
      "entry": 185.50,
      "stop": 180.00,
      "target": 195.00,
      "shares": 36,
      "max_risk": 198.00,
      "max_reward": 342.00,
      "r_multiple": 1.73,
      "breakeven": 185.50
    },
    {
      "type": "put_credit_spread",
      "short_strike": 180,
      "long_strike": 175,
      "expiration": "2025-03-21",
      "premium_collected": 1.85,
      "max_risk": 315.00,
      "max_reward": 185.00,
      "pop_estimate": 0.72,
      "breakeven": 178.15,
      "contracts": 1
    },
    {
      "type": "naked_put",
      "strike": 180,
      "expiration": "2025-03-21",
      "premium": 3.20,
      "max_risk": 17680.00,
      "breakeven": 176.80,
      "pop_estimate": 0.68,
      "margin_required": 3600.00,
      "assignment_cost": 18000.00
    },
    {
      "type": "call_debit_spread",
      "long_strike": 185,
      "short_strike": 195,
      "expiration": "2025-03-21",
      "cost": 3.50,
      "max_risk": 350.00,
      "max_reward": 650.00,
      "breakeven": 188.50,
      "pop_estimate": 0.42
    }
  ]
}
```

---

## Strategy Module Interface

Every strategy lives in `strategies/` and implements this interface:

```python
class BaseStrategy:
    """Base class for all scanning strategies."""

    id: str                  # slug identifier
    name: str                # display name
    description: str         # what it looks for
    source: str              # where you learned it
    parameters: dict         # configurable thresholds
    references: list[str]    # links to wiki, books, videos, etc.

    def scan(self, universe: list[str], market_data: dict) -> list[ScanResult]:
        """
        Run the scan against a universe of tickers.
        Returns list of tickers that match criteria with signal metadata.
        """
        raise NotImplementedError

    def describe_signal(self, signal_data: dict) -> str:
        """Human-readable explanation of why this ticker triggered."""
        raise NotImplementedError
```

### Starter Strategies to Implement

**1. EMA Pullback with Relative Strength (RDT core)**
- Stock above rising 50 and 200 DMA
- Pulling back to 8 or 21 EMA
- Relative strength vs SPY over 10-day lookback (stock % change > SPY % change)
- Volume on pullback lighter than breakout volume
- Parameters: ema_fast (8), ema_slow (21), rs_lookback (10), min_rs_ratio (1.0)

**2. AVWAP Support Bounce (Shannon)**
- Price approaching AVWAP from significant pivot (earnings, 52w high, IPO date)
- Relative strength positive
- Parameters: avwap_anchors (list of anchor types), proximity_pct (how close to AVWAP)
- Note: AVWAP calculation requires anchor date input — may need manual config per ticker or auto-detect earnings dates

**3. Sector Relative Strength Rotation**
- Identify strongest sectors (via sector ETFs: XLK, XLF, XLE, etc.)
- Surface top RS stocks within strongest sectors
- Parameters: sector_etfs (list), lookback (20), top_n_sectors (3), top_n_stocks (5)

**4. [Template] Custom Strategy**
- Empty template for adding new strategies quickly
- Copy, rename, implement scan() and describe_signal()

---

## Scan Universe

Default universe options (configurable):
- **S&P 500** — good starting point, liquid, options available
- **Custom watchlist** — user-defined ticker list
- **Sector ETFs** — for sector-level scanning
- Stored in `config/universe.json` or database table

---

## Phase 1 — Scanner + Stock Risk Calculator (BUILD THIS FIRST)

### What it does
1. User opens web UI, clicks "Run Scan" (or it auto-runs on schedule)
2. Scanner runs all active strategies against the configured universe
3. Results displayed in a table: Ticker | Strategy | Signal | Price | RS Score | Key Levels
4. Tickers that triggered multiple strategies are highlighted (convergence)
5. Clicking a ticker opens detail view with:
   - Current price, key EMA levels, 50/100/200 DMA
   - Relative strength score vs SPY
   - Suggested stop loss (below recent swing low or ATR-based)
   - Position size calculator: given account size + risk %, how many shares
   - R-multiple at 1R, 2R, 3R targets
   - Simple chart would be nice but not required for MVP — link to TradingView chart instead

### UI Layout (simple)
```
[Header: Trading Workstation]

[Sidebar]
  - Dashboard (today's scans)
  - Strategies (manage/configure)
  - Watchlist (bookmarked candidates)
  - Outcomes (tracking)
  - Settings (account config)

[Main Area]
  - Scan Results Table (sortable, filterable by strategy)
  - Click row -> Detail Panel (risk calc, levels, notes)
```

### Daily Workflow
1. Morning: Open app, run scan (or it ran overnight)
2. Review candidates, note convergence signals
3. Click interesting ones, check risk/reward math
4. Bookmark candidates you want to watch
5. End of day/next day: Outcomes tracker updates automatically

---

## Phase 2 — Options Overlay (AFTER Phase 1 is in daily use)

### What it adds
- For any candidate, click "Analyze Options"
- System pulls options chain from yfinance
- Presents side-by-side comparison of trade structures:
  - Stock with stop loss
  - Put Credit Spread (PCS)
  - Naked Put
  - Call Debit Spread (CDC)
  - Long Call (with delta/theta/vega)
- Each structure shows: max risk, max reward, breakeven, PoP estimate, R-multiple, capital required
- Position sizing respects account risk rules across all structures
- IV Rank context (is IV high or low relative to its range — informs whether to be a buyer or seller of premium)

### Options Math Notes
- PoP (Probability of Profit): Use delta of short strike as rough proxy for spreads. For more accuracy, implement basic BSM probability calculation.
- IV Rank: (Current IV - 52w Low IV) / (52w High IV - 52w Low IV). Simple but useful.
- Greeks: At minimum display delta, theta, vega for any options position.
- Position sizing for options: Risk = max loss per contract * number of contracts. Must stay within risk_per_trade * account_size.
- yfinance options data is delayed 15-20 min and sometimes unreliable. Display a "data as of" timestamp. Do NOT treat as execution-grade.

---

## Phase 3 — Outcome Tracker + Playbook (AFTER Phase 2)

### What it adds
- Automatic daily job that updates price data for all bookmarked candidates
- Dashboard showing: which strategy's picks performed best, convergence signal hit rate, average R achieved
- Strategy playbook page: for each strategy, see description, source references, historical performance of its picks, personal notes
- Cross-reference view: "show me all tickers that triggered Strategy A AND Strategy B"

---

## Phase 4 — Journal Layer (AFTER Phase 3)

### What it adds
- For candidates with status "entered", add execution details: actual entry, actual stop, actual exit, fees
- Pre-trade checklist (configurable per strategy): market conditions, sector, conviction level
- Post-trade review: grade execution separate from outcome (poker-style process review)
- Analytics: win rate by strategy, by market condition, by conviction level, avg R-multiple, expectancy

---

## Configuration

### config/settings.yaml
```yaml
account:
  size: 10000           # starting trading account (adjust to actual)
  risk_per_trade: 0.005  # 0.5%
  max_positions: 5

scanner:
  universe: "sp500"      # or "custom" or "sector_etfs"
  custom_tickers: []     # if universe is "custom"
  auto_run_time: "08:00" # optional scheduled scan

strategies:
  active:
    - ema_pullback_rs
    - avwap_bounce
    - sector_rotation
```

---

## File Structure

```
trading-workstation/
├── run.py                    # entry point
├── config/
│   ├── settings.yaml
│   └── universe.json
├── app/
│   ├── main.py               # FastAPI app
│   ├── models.py              # SQLAlchemy models
│   ├── database.py            # DB setup
│   ├── routers/
│   │   ├── scanner.py         # scan endpoints
│   │   ├── candidates.py      # watchlist/bookmark endpoints
│   │   ├── outcomes.py        # tracking endpoints
│   │   ├── options.py         # options analysis endpoints (Phase 2)
│   │   └── strategies.py      # strategy management
│   ├── services/
│   │   ├── market_data.py     # yfinance wrapper
│   │   ├── risk_calculator.py # position sizing, R-multiples
│   │   ├── options_math.py    # BSM, Greeks, PoP (Phase 2)
│   │   └── outcome_tracker.py # daily price update job
│   └── strategies/
│       ├── base.py            # BaseStrategy class
│       ├── ema_pullback_rs.py
│       ├── avwap_bounce.py
│       ├── sector_rotation.py
│       └── _template.py       # copy for new strategies
├── frontend/
│   ├── index.html
│   ├── static/
│   │   ├── style.css
│   │   └── app.js
│   └── templates/             # if using Jinja2
├── tests/
│   ├── test_strategies.py
│   ├── test_risk_calc.py
│   └── test_options_math.py
├── requirements.txt
└── README.md
```

---

## Claude Code Instructions

**Start with Phase 1 only.** Build the full data model (all tables) so the architecture supports future phases, but only implement the scanner + stock risk calculator + web UI for Phase 1.

Priority order:
1. Data model + database setup
2. Market data service (yfinance wrapper with caching)
3. BaseStrategy class + EMA Pullback RS strategy
4. Scanner service that runs strategies
5. Risk calculator (position sizing, R-multiples, stop/target math)
6. FastAPI routes for scan, results, candidates
7. Web UI — clean, functional, not pretty. Table of results, click for detail panel.
8. Account configuration page

**Important notes for Claude Code:**
- Use type hints throughout
- Add docstrings to all strategy methods
- Cache yfinance data aggressively (at least per-session, ideally daily cache in SQLite)
- Handle yfinance failures gracefully — some tickers will fail, don't crash the scan
- The strategy module system must be truly pluggable — registration via discovery, not hardcoded imports
- Include a `make run` or simple startup command
- Test the scanner with a small universe first (e.g. 10-20 tickers) before running against S&P 500

---

## Context Checkpoint

This spec represents the agreed architecture for a modular trading workstation. Key decisions:
- Local-first, Python/FastAPI/SQLite stack
- Pluggable strategy modules (not hardcoded to RDT)
- Four-phase build: Scanner → Options → Outcomes → Journal
- Options analysis compares multiple trade structures side-by-side
- Risk math is precise, respects account-level rules
- Cross-referencing and convergence signals are first-class features
- Free data only (yfinance) for now, with awareness of its limitations
