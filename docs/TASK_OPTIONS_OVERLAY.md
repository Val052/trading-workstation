# TASK: Options Overlay — Trade Structure Comparison Engine

## Context

The scanner produces hits with entry price, stop loss, and targets. The risk calculator sizes stock positions. But the question "should I trade this as stock, a call, or a spread?" has no answer in the system yet. This module closes that gap.

The Options Overlay takes any scanner hit or candidate and generates side-by-side comparisons of 4 trade structures: Stock, Long Call, Bull Call Spread, and Bull Put Spread. Each structure is sized to the same account risk rules (2% max), with precise risk/reward, Greeks, probability estimates, and a recommendation score.

This is NOT a standalone module. It lives inside the Scanner module as a service + router extension, filling the existing `options_analysis` JSON field on the Candidate model.

---

## Data Source

yfinance provides options chains with:
- Multiple expirations (weeklies through LEAPS)
- Strike prices with bid/ask/last/volume/OI
- **Implied volatility per contract** (critical — no need to compute IV ourselves)

Greeks are computed via Black-Scholes using the IV from yfinance.

---

## Architecture

```
modules/scanner/
├── services/
│   ├── options_chain.py      # NEW — chain fetching, filtering, caching
│   ├── options_greeks.py     # NEW — Black-Scholes Greeks calculator
│   ├── options_structures.py # NEW — trade structure builder + comparison
│   └── risk_calculator.py    # EXISTING — extend with options position sizing
├── routers/
│   └── options.py            # NEW — API endpoints
└── models.py                 # EXISTING — uses Candidate.options_analysis JSON field
```

No new database tables. All options analysis is ephemeral (computed on demand) or stored in the existing `Candidate.options_analysis` JSON field when a candidate is bookmarked.

---

## Service 1: `services/options_chain.py`

Fetches and filters options chain data from yfinance.

### Functions

#### `fetch_chain(ticker: str, min_dte: int = 14, max_dte: int = 90) -> dict`

Fetches all available chains within the DTE window. Returns structured dict:

```python
{
    "ticker": "AAPL",
    "underlying_price": 264.18,
    "dividend_yield": 0.0039,
    "chains": {
        "2026-03-20": {
            "dte": 20,
            "calls": [
                {
                    "strike": 265.0,
                    "bid": 5.20,
                    "ask": 5.40,
                    "mid": 5.30,
                    "iv": 0.214,
                    "volume": 1200,
                    "open_interest": 5600,
                    "itm": False,
                    "delta": 0.48,  # computed
                    "gamma": 0.02,
                    "theta": -0.15,
                    "vega": 0.18,
                },
                ...
            ],
            "puts": [ ... same structure ... ],
        },
        ...
    },
}
```

**Key behaviors:**
- Filter expirations to `min_dte` through `max_dte` (default 14-90 DTE)
- Filter strikes to +/- 15% of underlying price (skip deep ITM/OTM noise)
- Compute mid price as `(bid + ask) / 2`
- Compute Greeks for each contract using `options_greeks.py`
- Skip contracts with zero bid (illiquid)
- Cache result for 5 minutes (options data is semi-stale anyway with yfinance)

#### `select_expiry(chains: dict, target_dte: int) -> str`

Pick the expiration date closest to `target_dte`. For swing trades (5-20 day hold), default target is `2.5 * expected_hold_days` rounded to nearest available expiry, minimum 21 DTE. Prefers monthly expirations over weeklies (better liquidity) if within 5 days of target.

#### `select_strikes(chain_for_expiry: dict, underlying: float, strategy: str, stop: float, target: float) -> dict`

Smart strike selection based on strategy type:

| Structure | Long Strike | Short Strike | Logic |
|-----------|------------|-------------|-------|
| Long Call | ATM or 1 strike ITM | — | Delta 0.50-0.60 for good directional exposure |
| Bull Call Spread | ATM or 1 strike ITM | Near target price | Long delta ~0.55, short delta ~0.30 |
| Bull Put Spread | Near stop price | 1-2 strikes below long | Short delta ~-0.35, long delta ~-0.20 |

**Liquidity filter:** Skip strikes where `open_interest < 100` or `bid == 0` or spread `(ask - bid) / mid > 0.10` (10% wide = illiquid).

---

## Service 2: `services/options_greeks.py`

Black-Scholes Greeks calculator. Pure math, no external dependencies beyond `math` and `scipy.stats.norm`.

### Functions

#### `bs_price(S, K, T, r, sigma, option_type="call") -> float`

Standard Black-Scholes price.
- `S` = underlying price
- `K` = strike
- `T` = time to expiry in years (DTE / 365)
- `r` = risk-free rate (default 0.045 — updated from treasury data if available)
- `sigma` = implied volatility (from yfinance)

#### `bs_greeks(S, K, T, r, sigma, option_type="call") -> dict`

Returns:
```python
{
    "delta": float,    # rate of change vs underlying
    "gamma": float,    # rate of change of delta
    "theta": float,    # daily time decay in dollars
    "vega": float,     # sensitivity to 1% IV change
    "rho": float,      # sensitivity to interest rate (minor)
}
```

**Implementation notes:**
- Theta returned as daily (divide annual by 365), negative for long options
- Vega scaled to 1% IV move (multiply raw vega by 0.01)
- Use `scipy.stats.norm.cdf` and `norm.pdf` — scipy is already available
- Handle edge cases: T <= 0 returns intrinsic value only, sigma <= 0 returns 0

#### `probability_of_profit(S, K, T, r, sigma, option_type, premium_paid) -> float`

Probability that the option expires above breakeven (for calls: strike + premium).
Uses the Black-Scholes probability framework:
- Long Call PoP = N(d2) where d2 uses breakeven as strike
- Long Put PoP = N(-d2) where d2 uses breakeven as strike
- Adjust for spread structures in the structures service

#### `probability_of_touch(S, K, T, sigma) -> float`

Probability that the underlying touches a given price level before expiry. Useful for target probability. Approximation: `2 * probability_itm_at_expiry` (barrier option approximation, valid for ATM-ish levels).

---

## Service 3: `services/options_structures.py`

The core comparison engine. Takes a trade setup (entry, stop, target) and builds all 4 structures side by side.

### Data Classes

```python
@dataclass
class StructureAnalysis:
    """One complete trade structure analysis."""
    structure_type: str          # "stock", "long_call", "bull_call_spread", "bull_put_spread"
    display_name: str            # "Stock", "Long Call", "Bull Call Spread", "Bull Put Spread"

    # Position
    contracts: int               # number of contracts (or shares for stock)
    contract_size: int           # 100 for options, 1 for stock
    total_units: int             # contracts * contract_size

    # Legs (list of dicts, each with: type, strike, expiry, action, price, greeks)
    legs: list

    # Risk/Reward
    max_risk: float              # maximum dollar loss
    max_reward: float            # maximum dollar gain (None = unlimited for long call)
    breakeven: float             # breakeven price at expiry
    risk_reward_ratio: float     # max_reward / max_risk

    # Position sizing
    capital_required: float      # margin or debit required
    capital_as_pct: float        # capital_required / account_size
    risk_as_pct: float           # max_risk / account_size

    # Probabilities
    prob_profit: float           # probability of any profit at expiry
    prob_target: float           # probability of reaching target_1
    prob_max_loss: float         # probability of max loss (full premium loss / stop hit)

    # Greeks (position-level)
    position_delta: float        # net delta * contracts * 100
    position_gamma: float
    position_theta: float        # daily decay in dollars
    position_vega: float

    # Time decay
    theta_as_pct_of_risk: float  # daily theta / max_risk — "how fast am I bleeding"

    # Scoring
    score: float                 # 0-100 composite recommendation score
    score_rationale: str         # why this score

    # Expiry info (None for stock)
    expiry: str | None
    dte: int | None
```

### Main Function

#### `compare_structures(ticker, entry, stop, target, account_size, risk_per_trade, chains_data) -> dict`

Returns:
```python
{
    "ticker": "AAPL",
    "underlying_price": 264.18,
    "setup": {"entry": 264.18, "stop": 258.0, "target": 278.0},
    "structures": [
        StructureAnalysis(structure_type="stock", ...),
        StructureAnalysis(structure_type="long_call", ...),
        StructureAnalysis(structure_type="bull_call_spread", ...),
        StructureAnalysis(structure_type="bull_put_spread", ...),
    ],
    "recommendation": {
        "best": "bull_call_spread",
        "rationale": "Best risk/reward ratio (3.2:1) with defined risk and lowest capital requirement. Probability of profit 52% with manageable theta decay.",
    },
    "warnings": [
        "Earnings on 2026-04-24 — before expiry. IV crush risk on all options structures.",
        "Bid-ask spread on 265 put is 8% — consider limit orders.",
    ],
}
```

### Structure Builders (internal functions)

#### `_build_stock(entry, stop, target, account_size, risk_per_trade) -> StructureAnalysis`

The baseline. Uses existing `risk_calculator.calculate_risk()` logic:
- `contracts` = position_size (shares)
- `max_risk` = shares * (entry - stop)
- `max_reward` = shares * (target - entry)
- `prob_profit` = not applicable (no expiry), set to None
- `score` = baseline 50 (neutral reference)

#### `_build_long_call(entry, stop, target, account_size, risk_per_trade, chain) -> StructureAnalysis`

- Strike selection: ATM or 1 strike ITM (delta 0.50-0.60)
- Expiry selection: 2.5x expected hold period, minimum 21 DTE
- Position sizing: `contracts = floor(max_dollar_risk / (ask_price * 100))`
- `max_risk` = premium * contracts * 100 (total debit)
- `max_reward` = unlimited (for display: compute at target price)
- `breakeven` = strike + premium
- `prob_profit` = P(S > breakeven at expiry)
- `prob_target` = P(S > target at expiry)
- Greeks: scale per-contract greeks by contracts

**Score factors:**
- Reward/risk ratio vs stock (higher = better)
- Theta decay rate relative to expected hold (fast decay = penalty)
- Probability of profit (higher = better)
- Liquidity of chosen strike (tight spread = bonus)
- Capital efficiency vs stock (less capital = bonus)

#### `_build_bull_call_spread(entry, stop, target, account_size, risk_per_trade, chain) -> StructureAnalysis`

Debit spread: Buy lower strike call, sell higher strike call.

- Long strike: ATM or 1 ITM (delta ~0.55)
- Short strike: near target (delta ~0.30)
- If no good short strike near target, use 1-2 strikes OTM from long
- `max_risk` = net debit * contracts * 100
- `max_reward` = (strike_width - net_debit) * contracts * 100
- `breakeven` = long_strike + net_debit
- Position sizing: `contracts = floor(max_dollar_risk / (net_debit * 100))`
- Probability: P(S > breakeven) for profit, P(S > short_strike) for max profit

**Score factors:**
- Defined risk (bonus vs long call)
- Risk/reward ratio (typically better than stock for similar setups)
- Reduced theta exposure vs naked long call
- Capped upside (penalty if target is well above short strike)

#### `_build_bull_put_spread(entry, stop, target, account_size, risk_per_trade, chain) -> StructureAnalysis`

Credit spread: Sell higher strike put, buy lower strike put.

- Short strike: near entry or slightly below (delta ~-0.35)
- Long strike: 1-2 strikes below short (near stop level)
- `max_risk` = (strike_width - credit) * contracts * 100
- `max_reward` = credit * contracts * 100
- `breakeven` = short_strike - credit
- Position sizing: `contracts = floor(max_dollar_risk / ((strike_width - credit) * 100))`
- Probability: P(S > breakeven) for profit

**Score factors:**
- Time decay works FOR you (theta positive — major advantage)
- Probability of profit typically >55% (bonus)
- Lower risk/reward ratio (credit received vs width at risk)
- No need for stock to move UP — just needs to stay above breakeven

### Scoring Algorithm

Each structure gets a 0-100 composite score:

```
score = (
    25 * normalized_risk_reward       +  # higher R:R = better
    20 * normalized_prob_profit        +  # higher PoP = better
    20 * capital_efficiency            +  # less capital tied up = better
    15 * theta_efficiency              +  # less bleeding (or positive theta) = better
    10 * liquidity_score               +  # tighter spreads, higher OI = better
    10 * probability_of_target            # higher P(target) = better
)
```

Where each component is normalized to 0-1 range:
- `normalized_risk_reward`: min(risk_reward_ratio / 5.0, 1.0) — 5:1 or better = max score
- `normalized_prob_profit`: prob_profit (already 0-1)
- `capital_efficiency`: 1 - (capital_required / stock_capital_required) — less capital = higher
- `theta_efficiency`: for positive theta (credit spreads) = 1.0; for negative theta = max(0, 1 - abs(daily_theta / max_risk))
- `liquidity_score`: based on bid-ask spread width and OI (1.0 if spread < 3% and OI > 500)
- `probability_of_target`: prob_target (already 0-1)

Stock always scores 50 as the baseline reference.

### Warnings Generator

#### `_generate_warnings(ticker, chains_data, structures) -> list[str]`

Check for:
- **Earnings before expiry**: fetch earnings date from yfinance `ticker.info.get('earningsDate')`, warn if before selected expiry (IV crush risk)
- **Wide bid-ask spreads**: any leg with spread > 5% of mid
- **Low open interest**: any leg with OI < 200
- **High IV rank**: if current IV is in top 20% of 52-week range, warn "IV elevated — options are expensive, consider selling premium"
- **Low IV rank**: if current IV is in bottom 20%, note "IV low — options are cheap, buying premium is favorable"
- **Dividend before expiry**: if ex-div date falls before expiry, early assignment risk on short calls
- **Position size = 0**: if max_dollar_risk is too small for even 1 contract, flag "Account risk budget too small for options on this ticker — consider stock only"

---

## Service Extension: `services/risk_calculator.py`

Add one function to existing file:

#### `calculate_options_risk(structure: StructureAnalysis, account_size: float) -> dict`

Returns position sizing context formatted for the Candidate model:
```python
{
    "structure_type": "bull_call_spread",
    "legs": [...],
    "contracts": 3,
    "max_risk": 450.0,
    "max_reward": 1050.0,
    "breakeven": 267.50,
    "risk_reward_ratio": 2.33,
    "account_risk_pct": 0.015,
    "capital_required": 450.0,
    "greeks": {"delta": 45.0, "theta": -3.20, "vega": 12.0},
    "expiry": "2026-03-20",
    "dte": 20,
    "prob_profit": 0.52,
}
```

This dict is what gets stored in `Candidate.options_analysis` when a candidate is bookmarked with an options structure.

---

## Router: `routers/options.py`

Prefix: `/api/scanner/options`

### Endpoints

#### `GET /api/scanner/options/chain/{ticker}`

Fetch filtered options chain for a ticker.

Query params:
- `min_dte`: int = 14
- `max_dte`: int = 90

Returns the full chain structure from `fetch_chain()`.

#### `POST /api/scanner/options/compare`

The main comparison endpoint. Generates side-by-side structure analysis.

Request body:
```json
{
    "ticker": "AAPL",
    "entry_price": 264.18,
    "stop_loss": 258.0,
    "target_1": 278.0,
    "scan_result_id": 42
}
```

Returns the full `compare_structures()` output.

#### `POST /api/scanner/options/bookmark`

Bookmark a candidate with a specific options structure.

Request body:
```json
{
    "scan_result_id": 42,
    "structure_type": "bull_call_spread",
    "stop_loss": 258.0,
    "target_1": 278.0
}
```

Creates a Candidate row with `trade_structure` = structure_type and `options_analysis` = the full structure dict. Uses the existing Candidate model — no schema changes.

---

## UI Updates

Add to the scanner detail panel (when a scan result is selected):

### 1. "Compare Structures" Button

Next to the existing risk calculator section. Clicking it calls `POST /api/scanner/options/compare` with the scan result's entry/stop/target.

### 2. Structure Comparison Cards

4 cards in a row (or 2x2 grid on smaller screens):

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   STOCK          │  │   LONG CALL      │  │  BULL CALL       │  │  BULL PUT        │
│   Score: 50      │  │   Score: 62      │  │  SPREAD          │  │  SPREAD          │
│                  │  │                  │  │  Score: 71 ★     │  │  Score: 68       │
│  Risk: $620      │  │  Risk: $530      │  │  Risk: $450      │  │  Risk: $380      │
│  Reward: $1,380  │  │  Reward: unlim   │  │  Reward: $1,050  │  │  Reward: $620    │
│  R:R: 2.2:1      │  │  R:R: 5.1:1      │  │  R:R: 2.3:1      │  │  R:R: 1.6:1      │
│  Breakeven: —    │  │  BE: $270.30     │  │  BE: $267.50     │  │  BE: $259.80     │
│                  │  │                  │  │                  │  │                  │
│  100 shares      │  │  1 contract      │  │  3 contracts     │  │  Capital: $380   │
│  Capital: $26.4k │  │  Capital: $530   │  │  Capital: $450   │  │                  │
│                  │  │                  │  │                  │  │  PoP: 61%        │
│  PoP: —          │  │  PoP: 41%        │  │  PoP: 52%        │  │  P(max): 61%     │
│  P(target): —    │  │  P(tgt): 28%     │  │  P(max): 28%     │  │                  │
│                  │  │                  │  │                  │  │  Θ: +$2.80/day   │
│  Θ: —            │  │  Θ: -$15.20/day  │  │  Θ: -$3.20/day   │  │  Δ: 32           │
│  Δ: 100          │  │  Δ: 55           │  │  Δ: 45           │  │                  │
└─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘
```

- Highest scoring card gets a star and subtle highlight border
- Score badge: color coded (green >65, yellow 40-65, red <40)
- Stock card is always the leftmost reference

### 3. Warnings Bar

Below the cards, yellow/orange bar with any warnings from the analysis.

### 4. Leg Detail Expandable

Each options card has an expand toggle showing:
- Individual legs with strike, expiry, bid/ask, IV, delta
- P&L at target price (not just max)
- P&L at stop price
- Theta decay over expected hold period (e.g., "Over 10 days: -$32 theta cost")

### 5. Bookmark with Structure

The existing "Bookmark" button gets a dropdown: "Bookmark as Stock" / "Bookmark as Long Call" / "Bookmark as Bull Call Spread" / "Bookmark as Bull Put Spread". Selected structure's data saved to `Candidate.options_analysis`.

---

## Integration with Existing Candidate Flow

The existing `/candidates/bookmark` endpoint should be extended (not replaced):

```python
class BookmarkRequest(BaseModel):
    scan_result_id: int
    stop_loss: float
    target_1: float
    target_2: Optional[float] = None
    trade_structure: str = "stock"  # NEW — "stock", "long_call", "bull_call_spread", "bull_put_spread"
```

When `trade_structure != "stock"`:
1. Fetch chain, run `compare_structures()` for just that structure
2. Store result in `Candidate.options_analysis`
3. Set `Candidate.trade_structure` to the selected type
4. Position size and risk numbers come from the options analysis, not stock calculation

---

## Edge Cases

- **Illiquid options**: If no strikes pass liquidity filter, return only Stock structure with warning "Options market illiquid for this ticker"
- **Account too small**: If `max_dollar_risk < minimum_option_cost` (cheapest available contract), flag "Account risk budget insufficient for options" and exclude that structure
- **No chain data**: yfinance occasionally returns empty chains. Retry once, then return Stock-only with error message
- **After hours / weekends**: Options prices are stale. Add timestamp and "Prices as of [last trade date]" notice
- **Penny stocks / low price**: If underlying < $10, options may not exist. Skip gracefully
- **Split-adjusted chains**: yfinance handles this, but verify contract size = "REGULAR" (skip non-standard)
- **Risk-free rate**: Default 4.5%. If you want accuracy, fetch ^TNX (10yr treasury yield) from yfinance and use that. Cache daily.

---

## Dependencies

- `scipy` — for `scipy.stats.norm` (Black-Scholes CDF/PDF). Already available in most Python environments. Add to requirements.txt if not present.
- No new pip packages beyond scipy.

---

## Testing Checklist

- [ ] `fetch_chain("AAPL")` returns chains with Greeks populated
- [ ] `fetch_chain("BRK-B")` handles ticker with hyphen
- [ ] `select_expiry()` picks monthly over weekly when within 5 days
- [ ] `select_strikes()` skips illiquid strikes (OI < 100, wide spread)
- [ ] `bs_greeks()` produces reasonable delta (0.5 for ATM call, ~0 for deep OTM)
- [ ] `bs_greeks()` theta is negative for long options, matches yfinance IV
- [ ] `compare_structures()` returns all 4 structures for AAPL
- [ ] `compare_structures()` returns only Stock when options illiquid (e.g., small-cap)
- [ ] Position sizing respects 2% account risk across all structures
- [ ] Bull put spread shows positive theta (time decay works for you)
- [ ] Warnings fire for: earnings before expiry, wide spreads, low OI, elevated IV
- [ ] Bookmark with `trade_structure="bull_call_spread"` stores options_analysis JSON
- [ ] Score ordering: stock = 50 baseline, options scored relative
- [ ] `probability_of_profit` is reasonable (40-60% for ATM structures)
- [ ] API endpoint returns within 5 seconds (chain fetch + computation)

---

## Build Order

1. `options_greeks.py` — pure math, no dependencies, test independently
2. `options_chain.py` — yfinance integration, uses greeks module
3. `options_structures.py` — the comparison engine, uses both above
4. `routers/options.py` — API endpoints
5. Extend `routers/candidates.py` BookmarkRequest to accept trade_structure
6. UI: comparison cards in scanner detail panel
7. UI: bookmark dropdown with structure selection

---

## What This Does NOT Do (Future Scope)

- Iron condors, strangles, calendars, diagonals (only directional structures for now)
- Real-time Greeks updates (computed once at comparison time)
- Backtesting options strategies against historical chains (yfinance doesn't have historical options data)
- Broker integration or order generation
- Portfolio-level Greeks aggregation (would live in Portfolio module)
- Options-specific outcome tracking (current tracker uses stock prices)
