# Claude Code Task: Platform Refactor + Portfolio Module

## Context

You are refactoring an existing trading workstation (FastAPI + SQLite + vanilla JS) from a monolithic scanner app into a modular platform architecture. Read `docs/PLATFORM_ARCHITECTURE.md` for the full architecture spec. The existing scanner code in `app/` works and must continue to work after the refactor.

## What Exists Now

- `app/main.py` — FastAPI app with scanner routes
- `app/models.py` — SQLAlchemy models (strategies, scan_results, candidates, outcomes, account_config, price_cache)
- `app/database.py` — SQLite setup
- `app/services/` — market_data.py, scanner.py, risk_calculator.py, universe.py
- `app/strategies/` — base.py, ema_pullback_rs.py, avwap_bounce.py, sector_rotation.py
- `app/routers/` — scanner.py, candidates.py, strategies.py, settings.py
- `frontend/index.html` + `frontend/static/` — current UI
- `config/settings.yaml` — current config
- `memory/` and `.claude/` — Skills layer (do not modify)

## Phase A: Platform Shell + Scanner Migration

### Step 1: Create platform layer

Create `platform/` directory:

```
platform/
├── __init__.py
├── app.py               # FastAPI app factory with module discovery
├── database.py          # Move from app/database.py, same SQLite setup
├── models/
│   ├── __init__.py
│   ├── base.py          # SQLAlchemy declarative base + common mixins (TimestampMixin with created_at/updated_at)
│   ├── instruments.py   # Instrument registry model (see PLATFORM_ARCHITECTURE.md)
│   └── events.py        # Event log model (see PLATFORM_ARCHITECTURE.md)
├── services/
│   ├── __init__.py
│   ├── market_data.py   # Move from app/services/market_data.py (shared service now)
│   ├── instrument_registry.py  # resolve_instrument(ticker_or_isin) -> Instrument
│   ├── event_log.py     # log_event(module, event_type, instrument_id, data) -> Event
│   ├── cache.py         # Move price caching logic from market_data into dedicated cache service
│   └── universe.py      # Move from app/services/universe.py
└── ui/
    ├── shell.html        # New: platform shell with sidebar + content area
    └── static/
        ├── shell.js      # Module routing, sidebar navigation, shared fetch helpers
        ├── shell.css     # Dark theme, shared typography, layout grid
        └── shared/       # Shared UI components (table renderer, detail panel, charts)
```

### Step 2: Create module base

Create `modules/`:

```
modules/
├── __init__.py
└── base.py              # BaseModule abstract class
```

BaseModule interface:
```python
from abc import ABC, abstractmethod
from fastapi import FastAPI

class BaseModule(ABC):
    id: str
    name: str
    icon: str  # CSS class or emoji for sidebar
    description: str
    order: int = 0  # sidebar sort order

    @abstractmethod
    def register_routes(self, app: FastAPI) -> None:
        """Register API routes. All routes must be under /api/{self.id}/"""

    @abstractmethod
    def get_models(self) -> list:
        """Return SQLAlchemy model classes for table creation"""

    def get_ui_assets(self) -> dict:
        """Return dict with panel_html, panel_js paths relative to platform/ui/"""
        return {
            "panel_html": f"module_panels/{self.id}.html",
            "panel_js": f"module_panels/{self.id}.js",
        }
```

### Step 3: Migrate scanner into module

Create `modules/scanner/`:
```
modules/scanner/
├── __init__.py          # ScannerModule(BaseModule) class
├── models.py            # Move Strategy, ScanResult, Candidate, Outcome, AccountConfig from app/models.py
├── routers/
│   ├── __init__.py
│   ├── scanner.py       # Move from app/routers/scanner.py
│   ├── candidates.py    # Move from app/routers/candidates.py
│   ├── strategies.py    # Move from app/routers/strategies.py
│   └── settings.py      # Move from app/routers/settings.py
├── services/
│   ├── __init__.py
│   ├── scanner.py       # Move from app/services/scanner.py
│   └── risk_calculator.py  # Move from app/services/risk_calculator.py
└── strategies/          # Move entire app/strategies/ directory
    ├── __init__.py
    ├── base.py
    ├── ema_pullback_rs.py
    ├── avwap_bounce.py
    ├── sector_rotation.py
    └── _template.py
```

ScannerModule class:
```python
class ScannerModule(BaseModule):
    id = "scanner"
    name = "Scanner"
    icon = "radar"
    description = "Strategy-based stock scanner with risk calculator"
    order = 1

    def register_routes(self, app):
        from .routers import scanner, candidates, strategies, settings
        app.include_router(scanner.router, prefix="/api/scanner", tags=["scanner"])
        app.include_router(candidates.router, prefix="/api/scanner", tags=["scanner"])
        app.include_router(strategies.router, prefix="/api/scanner", tags=["scanner"])
        app.include_router(settings.router, prefix="/api/scanner", tags=["scanner"])

    def get_models(self):
        from .models import Strategy, ScanResult, Candidate, Outcome, AccountConfig
        return [Strategy, ScanResult, Candidate, Outcome, AccountConfig]
```

### Step 4: Platform app factory

`platform/app.py`:
```python
import importlib
import pkgutil
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from platform.database import init_db, engine
from platform.models.base import Base

def discover_modules():
    """Auto-discover modules in the modules/ directory."""
    modules = []
    modules_path = Path(__file__).resolve().parent.parent / "modules"
    for importer, modname, ispkg in pkgutil.iter_modules([str(modules_path)]):
        if ispkg and modname != "__pycache__":
            mod = importlib.import_module(f"modules.{modname}")
            if hasattr(mod, "module_instance"):
                modules.append(mod.module_instance)
    return sorted(modules, key=lambda m: m.order)

def create_app() -> FastAPI:
    app = FastAPI(title="Trading Terminal", version="2.0.0")
    modules = discover_modules()

    @app.on_event("startup")
    def startup():
        # Create all platform tables + module tables
        Base.metadata.create_all(bind=engine)

    # Register module routes
    for mod in modules:
        mod.register_routes(app)

    # API endpoint: list available modules (for frontend sidebar)
    @app.get("/api/modules")
    def list_modules():
        return [{"id": m.id, "name": m.name, "icon": m.icon, "order": m.order} for m in modules]

    # Serve frontend
    UI_DIR = Path(__file__).resolve().parent / "ui"
    app.mount("/static", StaticFiles(directory=UI_DIR / "static"), name="static")
    app.mount("/panels", StaticFiles(directory=UI_DIR / "module_panels"), name="panels")

    @app.get("/")
    def serve_shell():
        return FileResponse(UI_DIR / "shell.html")

    return app
```

### Step 5: Create UI shell

The shell.html replaces frontend/index.html. It provides:
- **Header bar**: "Trading Terminal" title, instrument search input (for future use), refresh indicator
- **Sidebar**: dynamically populated from /api/modules endpoint. Each entry is a link that loads the corresponding module panel.
- **Content area**: loads module panel HTML/JS when sidebar item is clicked
- **Dark theme**: black/dark gray background, light text, accent color for interactive elements

The shell.js handles:
- Fetch /api/modules on load, render sidebar
- Click sidebar item -> fetch /panels/{module_id}.html and /panels/{module_id}.js -> inject into content area
- Shared utility functions: formatCurrency(), formatPercent(), formatDate(), fetchAPI(), renderTable()

**Create module panel files:**
- `platform/ui/module_panels/scanner.html` — move scanner-specific HTML from current frontend/index.html
- `platform/ui/module_panels/scanner.js` — move scanner-specific JS from current frontend
- `platform/ui/module_panels/portfolio.html` — new (Phase B)
- `platform/ui/module_panels/portfolio.js` — new (Phase B)

### Step 6: Update imports and test

- Update `run.py` to use `platform.app.create_app()` instead of importing from `app.main`
- Update all internal imports in scanner module (references to app.services, app.models, etc.)
- Scanner module uses `platform.services.market_data` and `platform.services.universe` (shared services)
- Scanner module uses its own `modules.scanner.models` and `modules.scanner.services.*`
- Test: `make run` should start the terminal, sidebar should show "Scanner" module, clicking it should show the scanner UI working exactly as before
- The `app/` directory can be kept temporarily for reference, then removed once migration is verified

### Step 7: Wire event log into scanner

- After a scan run completes, log_event("scanner", "scan_run", None, {"strategy": ..., "results_count": ..., "universe": ...})
- When user bookmarks a candidate, log_event("scanner", "candidate_bookmarked", instrument_id, {"strategy": ..., "entry": ..., "stop": ...})

---

## Phase B: Portfolio Module

### Step 1: Create module structure

```
modules/portfolio/
├── __init__.py          # PortfolioModule(BaseModule) class, module_instance
├── models.py            # PortfolioHolding, PortfolioSnapshot
├── routers/
│   ├── __init__.py
│   └── portfolio.py     # CRUD + enrichment + analytics endpoints
└── services/
    ├── __init__.py
    └── enrichment.py    # Per-holding and portfolio-level metric calculation
```

### Step 2: Implement models

See PLATFORM_ARCHITECTURE.md for the full schema. Key points:
- `portfolio_holdings` stores the static position data (instrument, shares, cost basis)
- `portfolio_snapshots` stores point-in-time portfolio state for historical tracking
- All models inherit from platform's Base
- Holdings reference instruments via instrument_id FK

### Step 3: Implement enrichment service

`modules/portfolio/services/enrichment.py`:

The enrichment service takes a list of holdings and returns enriched data. It uses `platform.services.market_data` for price data.

```python
def enrich_holding(holding: PortfolioHolding, market_data_service) -> dict:
    """Fetch current price and compute all per-holding metrics."""
    # Get current price, 50DMA, 200DMA, 52w high/low, ATR from market_data_service
    # Compute: market_value, unrealized_pnl, weight (needs total_value from caller)
    # Compute: vs_50dma_pct, vs_200dma_pct, dma50_slope, dma200_slope
    # Compute: rs_vs_spy (10-day relative strength)
    # For EUR conversion: fetch EURUSD=X rate
    # For non-marketable (cash, real_estate): skip price fetch, value = manual
    return enriched_dict

def enrich_portfolio(holdings: list[PortfolioHolding], market_data_service) -> dict:
    """Compute portfolio-level analytics."""
    # Enrich each holding
    # Compute: total_value, total_cost, total_pnl
    # Compute: allocation_by_asset_class, allocation_by_sector, allocation_by_account
    # Compute: concentration (max_weight, top5_weight, herfindahl)
    # Compute: breadth (pct_above_50dma, pct_above_200dma)
    # Compute: currency_exposure
    return portfolio_summary
```

### Step 4: Implement API routes

All routes under `/api/portfolio/`:

```python
@router.get("/holdings")      # List all active holdings with enrichment (optional ?enrich=true query param)
@router.post("/holdings")     # Add holding: {instrument_input, shares, cost_basis, cost_basis_currency, account_label, asset_class, notes}
@router.put("/holdings/{id}") # Update holding
@router.delete("/holdings/{id}")  # Soft delete (set is_active=false)
@router.get("/summary")       # Portfolio-level analytics (calls enrich_portfolio)
@router.post("/snapshot")     # Save current state to portfolio_snapshots
@router.get("/snapshots")     # List historical snapshots
@router.get("/holdings/{id}/detail")  # Full enriched detail for one holding
@router.post("/refresh")      # Refresh all prices (triggers market_data fetches, updates cache)
```

For POST /holdings, the `instrument_input` field accepts either a ticker or ISIN. The route calls `instrument_registry.resolve_instrument(instrument_input)` to get or create the canonical instrument, then creates the holding linked to it.

For non-marketable assets (cash deposits, real estate), accept `instrument_type` in the POST body. If instrument_type is "cash" or "real_estate", create a custom instrument entry with manual valuation (shares field = amount for cash, manual value for real estate).

### Step 5: Implement UI panel

`platform/ui/module_panels/portfolio.html`:

Layout:
```
<div id="portfolio-panel">
  <!-- Summary bar -->
  <div class="portfolio-summary">
    <div class="metric">Total Value: <span id="total-value">--</span></div>
    <div class="metric">Cost: <span id="total-cost">--</span></div>
    <div class="metric">P&L: <span id="total-pnl">--</span></div>
    <div class="metric">Last Updated: <span id="last-updated">--</span></div>
    <button id="refresh-btn">Refresh Prices</button>
    <button id="snapshot-btn">Take Snapshot</button>
  </div>

  <!-- Holdings table -->
  <table id="holdings-table">
    <!-- Columns: Instrument | Type | Shares | Price | Value | Weight | P&L | P&L% | vs50DMA | vs200DMA | RS | Trend | Account -->
    <!-- Sortable by clicking column headers -->
    <!-- Click row to expand detail panel -->
  </table>

  <!-- Allocation section -->
  <div class="allocation-section">
    <!-- Simple bar charts or pie charts for: asset class, sector, account, currency -->
    <!-- Use plain HTML/CSS bars, no charting library needed for v1 -->
  </div>

  <!-- Add holding form (collapsible) -->
  <div class="add-holding-form">
    <input placeholder="ISIN or Ticker" id="instrument-input" />
    <input type="number" placeholder="Shares" id="shares-input" />
    <input type="number" placeholder="Cost per share" id="cost-input" />
    <select id="currency-input"><option>EUR</option><option>USD</option></select>
    <select id="asset-class-input">
      <option>equity</option><option>etf</option><option>fixed_income</option>
      <option>cash_equivalent</option><option>real_estate</option><option>commodity</option>
    </select>
    <input placeholder="Account label" id="account-input" />
    <button id="add-btn">Add Holding</button>
  </div>

  <!-- Portfolio health dashboard -->
  <div class="portfolio-health">
    <div>Breadth: <span id="breadth-50">--</span> above 50DMA | <span id="breadth-200">--</span> above 200DMA</div>
    <div>Top holding: <span id="top-concentration">--</span></div>
    <div>Currency: <span id="currency-breakdown">--</span></div>
  </div>
</div>
```

`platform/ui/module_panels/portfolio.js`:
- On panel load: fetch /api/portfolio/holdings?enrich=false (fast load, no price fetching)
- "Refresh Prices" button: POST /api/portfolio/refresh, then GET /api/portfolio/holdings?enrich=true
- Table sorting: client-side sort on column click
- Add holding: POST /api/portfolio/holdings, refresh table
- Snapshot: POST /api/portfolio/snapshot, show confirmation
- Allocation charts: render simple horizontal bar charts using CSS (div width proportional to %)

### Step 6: Wire event log

- POST /holdings -> log_event("portfolio", "holding_added", instrument_id, {shares, cost_basis, account})
- DELETE /holdings/{id} -> log_event("portfolio", "holding_removed", instrument_id, {shares})
- POST /snapshot -> log_event("portfolio", "snapshot_taken", None, {total_value, total_pnl})
- POST /refresh -> log_event("portfolio", "prices_refreshed", None, {holdings_count, duration_seconds})

---

## Important Notes for Claude Code

1. **Don't break the scanner.** After Phase A, the scanner must work exactly as before. Test it.
2. **Use the same SQLite database** (`data/terminal.db` — rename from `workstation.db`). All platform and module tables live in one DB.
3. **All models must inherit from the platform Base** (in `platform/models/base.py`), not define their own.
4. **Dark theme throughout.** Black/near-black background (#0d1117 or similar), light text (#e6edf3), accent color for interactive elements (#58a6ff). Match the existing scanner UI's dark aesthetic.
5. **No external JS/CSS frameworks.** Vanilla JS, vanilla CSS, fetch API. No npm, no build step. The only exception: if you want a lightweight charting library for allocation charts, use Chart.js from CDN — but simple CSS bar charts are preferred for v1.
6. **yfinance is slow.** The enrichment service must handle timeouts gracefully. Fetch prices in parallel (asyncio or ThreadPoolExecutor). Never let a single failed ticker block the whole portfolio refresh.
7. **Currency conversion.** For EUR/USD, fetch `EURUSD=X` from yfinance. Cache the rate. Display both local currency and EUR values.
8. **Instrument resolution is best-effort.** If yfinance can't resolve an ISIN (it often can't for European ETFs), allow manual instrument creation with just a name. The instrument registry shouldn't be a blocker for adding holdings.
9. **Keep the old `app/` directory** until Phase A is verified working. Then it can be removed in a separate commit.
10. **Update CLAUDE.md** after the refactor to reflect the new file structure and module system.
11. **PriceCache model** currently in app/models.py should move to platform level (shared cache) since both scanner and portfolio use it.
