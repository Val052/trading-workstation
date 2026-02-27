# Trading Terminal — Platform Architecture v2

## Vision

A personal Bloomberg-style terminal: a unified platform with independent functional modules sharing a common data layer, instrument universe, and UI shell. Each module is independently useful but can reference data from other modules. The system is designed for one human operator with AI assistance, not for multi-user or institutional deployment.

Long-term objective: a customized terminal combining automated scanning, portfolio intelligence, technical analysis, AI-powered research, and trade execution — all local-first with data sovereignty preserved.

## Architectural Principles

1. **Module system, not monolith.** Every functional domain (scanning, portfolio, options analysis, journaling, AI research) is a self-contained module with its own models, routes, services, and UI panel. Modules register themselves with the platform on startup.

2. **Shared services layer.** Market data, instrument resolution, event logging, and the UI shell are platform-level services available to all modules. No module implements its own data fetching or instrument lookup.

3. **Append-only event log.** Every meaningful action (scan run, position entry, thesis update, conviction change) is logged to a single events table with structured metadata. This is the raw material for analytics, journaling, and audit trail. Current state is derived from events, not stored separately (where practical).

4. **Instrument-centric data model.** The platform maintains a canonical instrument registry. ISINs, tickers, and other identifiers resolve to the same instrument. Every module references instruments by their canonical ID, enabling cross-module queries ("show me everything the platform knows about AAPL — scans, portfolio position, thesis, journal entries").

5. **UI shell with module panels.** The frontend is a single-page app with a persistent sidebar (module navigation) and a main content area that renders the active module's panel. Each module registers its sidebar entry and panel component. The shell provides shared chrome: header, instrument search bar, notification area.

6. **Progressive complexity.** Build each module to be useful at its simplest, then add depth. The portfolio tracker works with manual ISIN input before it ever needs automated data feeds. The scanner works with yfinance before it ever needs real-time data.

---

## Platform Layer

### Shared Services

```
platform/
├── services/
│   ├── market_data.py        # Unified data fetcher (yfinance now, MCP/Polygon later)
│   ├── instrument_registry.py # Canonical instrument resolution (ticker <-> ISIN <-> name <-> sector)
│   ├── event_log.py          # Append-only event logging
│   └── cache.py              # Shared price/data cache (SQLite-backed)
├── models/
│   ├── base.py               # SQLAlchemy base, common mixins
│   ├── instruments.py        # Instrument registry table
│   └── events.py             # Event log table
├── ui/
│   ├── shell.html            # Main layout: sidebar + content area + header
│   ├── shell.js              # Module registration, routing, shared UI behaviors
│   └── shell.css             # Platform-level styling (dark theme, consistent typography)
└── module_registry.py        # Module discovery and registration
```

### Instrument Registry Model

```
instruments
  id              TEXT PRIMARY KEY (canonical: ticker for US equities, ISIN for international)
  ticker          TEXT (US ticker symbol, nullable for non-US)
  isin            TEXT (International Securities Identification Number, nullable)
  name            TEXT (full company/fund name)
  instrument_type TEXT ("equity", "etf", "index", "bond", "crypto", "cash")
  currency        TEXT ("USD", "EUR", etc.)
  sector          TEXT (GICS sector, nullable)
  exchange        TEXT (nullable)
  metadata        JSON (flexible: country, market_cap_bucket, etc.)
  created_at      DATETIME
  updated_at      DATETIME
```

The registry auto-populates when any module first references an instrument. If you type "AAPL" in the scanner, the registry resolves it. If you enter "IE00B4L5Y983" (iShares Core MSCI World ISIN) in the portfolio, the registry resolves it. Both point to canonical instrument records.

### Event Log Model

```
events
  id              INTEGER PRIMARY KEY AUTOINCREMENT
  timestamp       DATETIME (UTC, auto-set)
  module          TEXT ("scanner", "portfolio", "journal", etc.)
  event_type      TEXT ("scan_run", "position_opened", "thesis_updated", "conviction_changed", etc.)
  instrument_id   TEXT FK -> instruments (nullable — some events are system-level)
  actor           TEXT ("system", "user", "ai_skill")
  data            JSON (event-specific payload — fully flexible)
  session_id      TEXT (groups related events within a single user session)
```

Every module writes to this table. No module reads from another module's tables directly — cross-module queries go through the event log or shared services.

### Module Interface

Each module implements:

```python
class BaseModule:
    id: str              # "scanner", "portfolio", "journal"
    name: str            # "Scanner", "Portfolio", "Journal"
    icon: str            # sidebar icon identifier
    description: str
    
    def register_routes(self, app: FastAPI) -> None:
        """Register API routes under /api/{module_id}/"""
        
    def register_models(self) -> list[Base]:
        """Return SQLAlchemy model classes for this module's tables"""
        
    def get_ui_config(self) -> dict:
        """Return frontend config: sidebar label, panel template, JS/CSS assets"""
```

Modules live in `modules/` directory. Platform discovers them on startup via entry points or directory scanning.

---

## Module 1: Scanner (existing — refactor into module structure)

The current scanner moves from `app/` into `modules/scanner/`. No functional changes needed — just reorganize into the module interface. All existing tables (strategies, scan_results, candidates, outcomes) become module-owned tables that the scanner registers.

### Migration path:
- Move `app/strategies/` -> `modules/scanner/strategies/`
- Move `app/services/scanner.py` -> `modules/scanner/services/scanner.py`
- Move `app/services/risk_calculator.py` -> `modules/scanner/services/risk_calculator.py`
- Move `app/routers/scanner.py`, `candidates.py`, `strategies.py` -> `modules/scanner/routers/`
- `market_data.py` and `universe.py` elevate to platform shared services
- Scanner writes to event log on every scan run and when user bookmarks a candidate

### Scanner UI panel:
- Same as current: scan results table, detail panel, candidate watchlist
- Now renders inside the platform shell instead of being the whole page

---

## Module 2: Portfolio Tracker (new)

### Purpose
Track long-term investment holdings separately from active trading. Input ISINs/tickers and share counts, see position distribution, exposure analysis, momentum, and trend metrics. This is a "net worth cockpit" for the investment portfolio, not a trading P&L tracker.

### Data Model

```
portfolio_holdings
  id              INTEGER PRIMARY KEY AUTOINCREMENT
  instrument_id   TEXT FK -> instruments
  shares          REAL (fractional shares allowed for ETFs/funds)
  cost_basis      REAL (average cost per share in instrument currency)
  cost_basis_currency TEXT (EUR, USD — for proper P&L calc)
  date_acquired   DATE (nullable — approximate is fine)
  account_label   TEXT ("IBKR", "index_fund", "money_market", "deposit", etc.)
  asset_class     TEXT ("equity", "fixed_income", "cash_equivalent", "real_estate", "commodity")
  notes           TEXT
  is_active       BOOLEAN DEFAULT TRUE (soft delete)
  created_at      DATETIME
  updated_at      DATETIME

portfolio_snapshots
  id              INTEGER PRIMARY KEY AUTOINCREMENT
  snapshot_date   DATE
  total_value     REAL
  total_cost      REAL
  total_pnl       REAL
  allocation_data JSON (breakdown by asset class, sector, geography, account)
  metrics_data    JSON (portfolio-level momentum, trend, risk metrics)
  created_at      DATETIME
```

### Enrichment Engine

When the portfolio loads (or on manual refresh), the system enriches each holding with live data from the shared market_data service:

**Per-holding metrics:**
- Current price + daily change (from yfinance or MCP)
- Market value = shares x current price
- Unrealized P&L = market value - (shares x cost_basis), both in instrument currency and portfolio base currency (EUR)
- Weight = market value / total portfolio value (as percentage)
- Momentum: price vs 50 DMA, price vs 200 DMA (above/below + distance %)
- Trend: 50 DMA slope direction (rising/falling/flat), 200 DMA slope direction
- Relative strength vs benchmark (SPY for US equities, MSCI World for intl)
- 52-week range position: (current - 52w low) / (52w high - 52w low)
- ATR (14-day) for volatility context

**Portfolio-level analytics:**
- Total value, total cost, total unrealized P&L
- Allocation by: asset class, sector (for equities/ETFs), geography, account/broker
- Concentration: largest position weight, top-5 concentration, Herfindahl index
- Trend health: % of holdings above 50 DMA, % above 200 DMA (portfolio breadth)
- Currency exposure breakdown (if holding non-EUR instruments)

### Portfolio UI Panel

**Layout:**
```
[Portfolio Header]
  Total Value: EUR XXX,XXX | Cost: EUR XXX,XXX | P&L: +EUR XX,XXX (+X.X%)
  Last Updated: HH:MM

[Holdings Table — sortable by any column]
  Instrument | Shares | Price | Value | Weight | P&L | P&L% | vs50DMA | vs200DMA | RS | Trend

[Allocation Charts]
  Asset Class pie | Sector breakdown | Account breakdown | Geography

[Portfolio Health]
  Breadth: X/Y above 50DMA | Concentration: top position X% | Currency: X% EUR, Y% USD
```

**Interactions:**
- Click holding row -> detail panel with full metrics, TradingView chart link
- Add holding: input ISIN or ticker, shares, cost basis, account label
- Edit/remove holdings
- Manual refresh button (re-fetch all prices)
- Snapshot button (save current state to portfolio_snapshots for historical tracking)

### Portfolio API Endpoints

```
GET    /api/portfolio/holdings          — list all active holdings with enrichment
POST   /api/portfolio/holdings          — add new holding
PUT    /api/portfolio/holdings/{id}     — update holding
DELETE /api/portfolio/holdings/{id}     — soft-delete (set is_active=false)
GET    /api/portfolio/summary           — portfolio-level analytics
POST   /api/portfolio/snapshot          — take point-in-time snapshot
GET    /api/portfolio/snapshots         — list historical snapshots
GET    /api/portfolio/holding/{id}/detail — full enriched detail for one holding
```

---

## Module 3: Thesis Tracker (future — designed now, built later)

Structured research notes per instrument. Conviction, horizon, key drivers, invalidation criteria. Auto-populated from scanner hits and portfolio holdings, manually editable. Replaces free-form notes with queryable structured data.

```
theses
  id              INTEGER PRIMARY KEY AUTOINCREMENT
  instrument_id   TEXT FK -> instruments
  thesis_text     TEXT (current thesis: "Long AAPL on AI monetization cycle, services margin expansion")
  conviction      INTEGER (1-5 scale)
  horizon         TEXT ("days", "weeks", "months", "years")
  key_drivers     JSON (["iPhone cycle", "Services revenue growth", "AI integration"])
  invalidation    TEXT ("Below $180 200DMA break with volume")
  status          TEXT ("active", "invalidated", "realized", "expired")
  created_at      DATETIME
  updated_at      DATETIME
```

Every thesis update writes to the event log. The thesis tracker panel shows a table of active theses, filterable by conviction, horizon, status. Clicking a thesis shows its full history (via event log).

---

## Module 4: Options Analyzer (existing Phase 2 spec — becomes a module)

The current PROJECT_SPEC.md Phase 2 (options overlay) becomes `modules/options/`. No spec changes needed — it already has the right architecture. It registers as a module and renders its own panel.

---

## Module 5: Journal (existing Phase 4 spec — becomes a module)

The current Phase 4 spec becomes `modules/journal/`. It draws from the event log for auto-populated entries rather than requiring manual reconstruction.

---

## Module 6: AI Research (future — Skills integration)

The existing Skills layer (Claude Code terminal commands) eventually gets a web UI panel where you can run `/analyze AAPL` from the terminal and see the output rendered in the platform, with reports stored in the event log and linked to instruments.

---

## File Structure (target state)

```
trading-terminal/
├── run.py
├── config/
│   ├── settings.yaml          # Platform + module config
│   └── universe.json
├── platform/
│   ├── __init__.py
│   ├── app.py                 # FastAPI app factory, module discovery
│   ├── models/
│   │   ├── base.py            # SQLAlchemy base
│   │   ├── instruments.py     # Instrument registry
│   │   └── events.py          # Event log
│   ├── services/
│   │   ├── market_data.py     # Unified data fetcher
│   │   ├── instrument_registry.py
│   │   ├── event_log.py
│   │   └── cache.py
│   └── ui/
│       ├── shell.html
│       ├── static/
│       │   ├── shell.js
│       │   ├── shell.css
│       │   └── shared/        # Shared UI components (tables, charts, panels)
│       └── module_panels/     # Each module drops its panel HTML/JS here
│           ├── scanner.html
│           ├── scanner.js
│           ├── portfolio.html
│           └── portfolio.js
├── modules/
│   ├── __init__.py
│   ├── base.py                # BaseModule interface
│   ├── scanner/
│   │   ├── __init__.py        # ScannerModule class
│   │   ├── models.py          # strategies, scan_results, candidates, outcomes
│   │   ├── routers/
│   │   ├── services/
│   │   └── strategies/
│   └── portfolio/
│       ├── __init__.py        # PortfolioModule class
│       ├── models.py          # portfolio_holdings, portfolio_snapshots
│       ├── routers/
│       │   └── portfolio.py
│       └── services/
│           └── enrichment.py  # Per-holding and portfolio-level metric calculation
├── memory/                    # Skills layer persistent memory (unchanged)
├── .claude/                   # Skills definitions (unchanged)
├── data/
│   └── terminal.db            # Renamed from workstation.db
├── docs/
│   ├── PROJECT_SPEC.md        # Original spec (historical reference)
│   └── PLATFORM_ARCHITECTURE.md  # This document
├── tests/
├── requirements.txt
├── Makefile
└── CLAUDE.md
```

---

## Migration Strategy (from current codebase)

This is a refactor, not a rewrite. The existing code works. We reorganize it into the module structure and add the platform layer around it.

### Phase A: Platform Shell + Module Registry (do first)
1. Create `platform/` directory with app factory, base models (instruments, events), shared services
2. Create `modules/` directory with BaseModule interface
3. Move existing `app/` code into `modules/scanner/`, adapting imports
4. Create UI shell that renders scanner module in a sidebar-navigable layout
5. Verify everything still works exactly as before

### Phase B: Portfolio Module (do second)
1. Create `modules/portfolio/` with models, routers, services, UI panel
2. Implement holdings CRUD + enrichment engine
3. Add portfolio panel to UI shell sidebar
4. Wire up instrument registry (portfolio inputs resolve to canonical instruments)
5. Add portfolio events to event log (holding added, removed, snapshot taken)

### Phase C: Thesis Tracker (do when ready)
### Phase D: Options Module (existing Phase 2 spec)
### Phase E: Journal Module (existing Phase 4 spec)
### Phase F: AI Research Panel (Skills web integration)

---

## Technical Notes

### Currency Handling
Base currency is EUR. US equities are priced in USD. The enrichment engine needs EUR/USD conversion for proper portfolio-level P&L. yfinance provides `EURUSD=X` for this. Store both local-currency and EUR values.

### Instrument Resolution Logic
1. If input looks like an ISIN (2-letter prefix + 10 chars), resolve via ISIN
2. If input looks like a ticker (short alphabetic string), resolve via yfinance
3. If instrument not in registry, auto-create from yfinance metadata (name, sector, exchange)
4. If yfinance can't resolve, create with manual name entry (for deposits, real estate, etc.)

### Non-Marketable Assets
The portfolio should be able to track non-market assets for total net worth view:
- Cash deposits: instrument_type="cash", no price enrichment needed, value = shares (amount)
- Real estate: instrument_type="real_estate", manual valuation, no price enrichment
- Money market: can be tracked as cash equivalent with manual yield annotation

### Data Refresh Strategy
- No auto-refresh on page load (yfinance is slow for many holdings)
- Manual "Refresh Prices" button that fetches all instruments in parallel
- Cache prices in shared cache service (same as scanner's price_cache, now platform-level)
- Display "last updated" timestamp prominently

### UI Framework Decision
Keep the current approach: server-rendered HTML + vanilla JS + fetch API calls. No React, no build step. The shell is a single HTML file with JS module loading for each panel. This is fast to develop, easy to debug, and doesn't add toolchain complexity. If the UI eventually needs more sophistication, migrate to a lightweight framework later — but right now the constraint is functionality, not UI polish.

---

## Context Checkpoint

This document defines the platform architecture for the trading terminal. Key decisions:

- **Platform + modules pattern** (like Bloomberg functions) — not monolithic app
- **Shared services**: market data, instrument registry, event log, cache — available to all modules
- **Instrument-centric**: everything resolves to canonical instruments for cross-module queries
- **Event log as backbone**: append-only log of all actions, raw material for analytics and journal
- **Portfolio tracker is separate from trading**: different module, different tables, no exposure cross-contamination until explicitly desired
- **Migration, not rewrite**: existing scanner code moves into module structure with minimal changes
- **UI stays simple**: HTML + vanilla JS, dark theme, no React build step
- **Two-phase build**: Phase A (platform shell + scanner migration) then Phase B (portfolio module)
- **Future modules designed but not built**: thesis tracker, options, journal, AI research
