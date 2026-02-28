# TASK: Trading Journal — Process Review & Execution Tracking

## Context

You've built systems that find setups (Scanner), assess market environment (Market Pulse), compare trade structures (Options Overlay), and track forward outcomes (Outcome Tracker). What's missing is the human layer — the record of YOUR decisions, YOUR execution, and YOUR process quality.

This is the poker logbook. In poker, the sophisticated player tracks not just "did I win the hand" but "did I play the hand correctly." A winning hand played badly is a leak. A losing hand played correctly is variance. The journal separates these two things, which is the single most important analytical distinction a developing trader can make.

The Outcome Tracker already answers "did the scanner's picks go up?" The Journal answers "when I actually took a trade, did I follow my process, and how did my execution compare to the theoretical edge?"

---

## Architecture

This is a new module: `modules/journal/`

The Journal connects to the Scanner module through the Candidate model. When a Candidate's status changes from "watching" to "entered", a TradeEntry is born. The journal owns everything from that point forward: execution details, checklists, reviews, and process analytics.

```
modules/journal/
├── __init__.py          # BaseModule registration
├── models.py            # TradeEntry, PreTradeCheck, PostTradeReview
├── services/
│   ├── __init__.py
│   ├── trade_lifecycle.py   # entry/exit/status transitions
│   ├── checklist.py         # pre-trade checklist logic
│   └── process_analytics.py # process quality metrics
├── routers/
│   ├── __init__.py
│   ├── trades.py            # trade CRUD + lifecycle endpoints
│   └── analytics.py         # process analytics endpoints
└── static/
    └── journal_panel.js     # UI panel
```

---

## Models: `models.py`

### TradeEntry

The core record. One per actual trade taken.

```python
class TradeEntry(Base):
    __tablename__ = "trade_entries"

    id: int                          # PK auto
    candidate_id: int                # FK -> candidates.id (nullable — manual trades allowed)
    scan_result_id: int | None       # FK -> scan_results.id (nullable — for provenance)

    # What
    ticker: str
    strategy_id: str                 # which strategy generated this (or "manual")
    trade_structure: str             # "stock", "long_call", "bull_call_spread", "bull_put_spread"
    direction: str                   # "long" or "short" (default "long")

    # Plan (from Candidate, captured at entry time — immutable snapshot)
    planned_entry: float
    planned_stop: float
    planned_target_1: float
    planned_target_2: float | None
    planned_position_size: int
    planned_r_multiple: float
    planned_risk_dollars: float

    # Execution (filled by user)
    actual_entry: float | None
    actual_entry_date: date | None
    actual_stop: float | None        # stop may be adjusted
    actual_size: int | None          # may differ from planned
    actual_exit: float | None
    actual_exit_date: date | None
    exit_reason: str | None          # "target_hit", "stopped_out", "time_exit", "discretionary", "trailing_stop"
    fees: float                      # default 0

    # Computed (auto-filled on exit)
    actual_r_multiple: float | None
    pnl_dollars: float | None
    pnl_percent: float | None
    hold_days: int | None
    slippage_entry: float | None     # actual_entry - planned_entry
    slippage_exit: float | None      # for stops: actual_exit - planned_stop

    # Context (auto-captured at entry time)
    regime_at_entry: str | None      # from Market Pulse
    regime_score_at_entry: float | None
    spy_price_at_entry: float | None
    vix_at_entry: float | None
    sector_rank_at_entry: str | None # e.g. "XLK: #2 of 11"

    # Process scores (from PostTradeReview, denormalized for fast queries)
    process_score: float | None      # 0-100 composite
    entry_grade: str | None          # A/B/C/D/F
    management_grade: str | None
    exit_grade: str | None

    # State
    status: str                      # "open", "closed", "cancelled"
    notes: str                       # free-form notes, appended over lifetime

    created_at: datetime
    updated_at: datetime
```

### PreTradeCheck

Structured checklist completed before entry. Enforces discipline.

```python
class PreTradeCheck(Base):
    __tablename__ = "pre_trade_checks"

    id: int
    trade_entry_id: int              # FK -> trade_entries.id

    # Market Context (auto-populated from Market Pulse)
    market_regime: str               # RISK_ON / RISK_OFF / ROTATION
    regime_score: float
    spy_trend: str                   # "above_rising_50dma", "below_falling_50dma", etc.

    # Strategy-Specific Checks (user responses, stored as JSON)
    checklist_responses: dict        # {"daily_trend_aligned": true, "volume_confirmed": true, ...}

    # Conviction & Sizing
    conviction_level: int            # 1-5 scale
    conviction_rationale: str        # WHY this conviction level (free text, required)
    risk_amount: float               # dollars at risk
    risk_percent: float              # % of account
    position_size_appropriate: bool  # user confirms sizing makes sense

    # Emotional State (honest self-assessment)
    emotional_state: str             # "calm", "excited", "fomo", "revenge", "bored", "confident"
    entering_for_right_reasons: bool # user acknowledges yes/no

    # Override Check
    deviating_from_plan: bool        # if true, must explain
    deviation_reason: str | None

    completed_at: datetime
```

### PostTradeReview

Completed after exit. Grades process quality independently of P&L.

```python
class PostTradeReview(Base):
    __tablename__ = "post_trade_reviews"

    id: int
    trade_entry_id: int              # FK -> trade_entries.id

    # Entry Execution (grade 1-5)
    entry_timing_score: int          # 1=terrible, 5=perfect. Did you enter at the planned level?
    entry_patience_score: int        # Did you wait for confirmation or chase?
    entry_notes: str

    # Trade Management (grade 1-5)
    stop_honored: bool               # Binary: did you honor the original stop?
    stop_moved: bool                 # Did you move the stop? (not inherently bad if trailing)
    stop_move_justified: bool | None # If moved: was it part of the plan?
    added_to_position: bool          # Did you add? Was it planned?
    management_notes: str

    # Exit Execution (grade 1-5)
    exit_timing_score: int           # Did you exit at plan, or panic/greed?
    exit_followed_plan: bool         # Did exit match one of: target, stop, time, trailing?
    exit_notes: str

    # Overall Process Assessment
    followed_strategy_rules: bool    # Did the trade match the strategy's criteria?
    emotional_influence: int         # 1=none, 5=heavily emotional. Lower is better.
    would_take_again: bool           # Knowing what you knew AT ENTRY, would you take it again?
    key_lesson: str                  # Required. What did you learn?

    # Computed Scores (auto from individual grades)
    entry_grade: str                 # A-F from entry scores
    management_grade: str            # A-F from management scores
    exit_grade: str                  # A-F from exit scores
    overall_process_score: float     # 0-100 composite

    completed_at: datetime
```

---

## Strategy-Specific Checklists

Each strategy has different entry criteria. The checklist is configured per strategy as a JSON template stored in the Strategy model (add a `checklist_template` JSON field to the existing Strategy model in scanner/models.py).

### Default Checklist Templates

**EMA Pullback RS:**
```json
{
    "items": [
        {"id": "spy_above_dma", "label": "SPY above rising 50 DMA?", "type": "boolean"},
        {"id": "daily_trend", "label": "Stock above rising 50/200 DMA?", "type": "boolean"},
        {"id": "pullback_to_ema", "label": "Price pulled back to 8/21 EMA zone?", "type": "boolean"},
        {"id": "rs_confirmed", "label": "Relative strength vs SPY positive?", "type": "boolean"},
        {"id": "volume_dry", "label": "Volume contracting on pullback?", "type": "boolean"},
        {"id": "sector_supportive", "label": "Sector showing relative strength?", "type": "boolean"},
        {"id": "risk_reward_ok", "label": "R:R at least 2:1?", "type": "boolean"}
    ]
}
```

**Trend Following:**
```json
{
    "items": [
        {"id": "breakout_confirmed", "label": "New 20D/50D high on close?", "type": "boolean"},
        {"id": "consolidation_prior", "label": "Consolidation visible before breakout?", "type": "boolean"},
        {"id": "volume_expansion", "label": "Volume above 20D average?", "type": "boolean"},
        {"id": "golden_cross", "label": "50 DMA above 200 DMA?", "type": "boolean"},
        {"id": "atr_stop_clear", "label": "ATR trailing stop gives enough room?", "type": "boolean"},
        {"id": "not_extended", "label": "Not extended >3% above channel?", "type": "boolean"}
    ]
}
```

**AVWAP Bounce:**
```json
{
    "items": [
        {"id": "avwap_proximity", "label": "Price within 2% of AVWAP level?", "type": "boolean"},
        {"id": "anchor_valid", "label": "AVWAP anchor point is significant (earnings/52w high)?", "type": "boolean"},
        {"id": "holding_avwap", "label": "Price holding/bouncing off AVWAP?", "type": "boolean"},
        {"id": "rs_positive", "label": "Relative strength positive?", "type": "boolean"},
        {"id": "market_supportive", "label": "Market not in risk-off?", "type": "boolean"}
    ]
}
```

**Sector Rotation:**
```json
{
    "items": [
        {"id": "sector_top3", "label": "Sector in top 3 RS ranking?", "type": "boolean"},
        {"id": "stock_leader", "label": "Stock is a leader within sector?", "type": "boolean"},
        {"id": "rotation_pattern", "label": "Rotation pattern matches thesis?", "type": "boolean"},
        {"id": "market_breadth", "label": "Breadth supports sector theme?", "type": "boolean"}
    ]
}
```

**Manual / No Strategy:**
```json
{
    "items": [
        {"id": "thesis_clear", "label": "Clear thesis for this trade?", "type": "boolean"},
        {"id": "stop_defined", "label": "Stop loss defined before entry?", "type": "boolean"},
        {"id": "target_defined", "label": "At least one target defined?", "type": "boolean"},
        {"id": "risk_sized", "label": "Position sized to risk rules?", "type": "boolean"}
    ]
}
```

Checklist items are always boolean for simplicity. The conviction rationale and emotional state capture the nuance.

---

## Service 1: `services/trade_lifecycle.py`

Manages the trade from entry to exit.

### Functions

#### `enter_trade(db, candidate_id, actual_entry, actual_size, notes) -> TradeEntry`

Transitions a Candidate to an active trade:

1. Load Candidate, verify status is "watching"
2. Create TradeEntry with planned fields snapshotted from Candidate
3. Auto-capture context:
   - Fetch latest RegimeSnapshot from Market Pulse (regime, score)
   - Fetch SPY price and VIX from market data
   - Look up sector rank from latest Market Pulse sectors data
4. Set `actual_entry`, `actual_size`
5. Compute `slippage_entry = actual_entry - planned_entry`
6. Update Candidate.status to "entered"
7. Log event
8. Return TradeEntry (checklist not yet completed — separate step)

#### `enter_manual_trade(db, ticker, entry, stop, target, size, strategy_id, structure, notes) -> TradeEntry`

For trades NOT originating from scanner. Creates TradeEntry without Candidate link.
Same context capture as above. `strategy_id` = "manual" if no strategy applies.

#### `update_trade(db, trade_id, fields) -> TradeEntry`

Update mutable fields on open trade: `actual_stop` (stop adjustment), `notes` (append), `actual_size` (partial exit). Cannot change planned fields.

#### `exit_trade(db, trade_id, actual_exit, exit_date, exit_reason, fees, notes) -> TradeEntry`

Close the trade:

1. Verify trade is "open"
2. Set exit fields
3. Compute:
   - `pnl_dollars = (actual_exit - actual_entry) * actual_size - fees` (adjusted for direction)
   - `pnl_percent = pnl_dollars / (actual_entry * actual_size)`
   - `actual_r_multiple = (actual_exit - actual_entry) / (actual_entry - planned_stop)` (using PLANNED stop as the risk reference, not actual)
   - `hold_days = (actual_exit_date - actual_entry_date).days`
   - `slippage_exit`: if stopped out, `actual_exit - planned_stop`; else None
4. Set status = "closed"
5. Update Candidate.status to "exited"
6. Log event
7. Return TradeEntry

**Why actual_r_multiple uses planned_stop:** The R-multiple must reference the risk you defined BEFORE the trade, not any adjusted stop. If you planned to risk $5/share but moved your stop tighter to $3/share and got stopped out, your actual R is computed against the original $5. This keeps R-multiples comparable across trades and prevents gaming the number by moving stops.

#### `cancel_trade(db, trade_id, reason) -> TradeEntry`

For trades entered but cancelled before meaningful execution (wrong ticker, immediate reversal, etc.). Sets status = "cancelled". Cancelled trades are excluded from performance analytics but visible in the log.

---

## Service 2: `services/checklist.py`

### Functions

#### `get_checklist_template(db, strategy_id) -> dict`

Returns the checklist template for a strategy. Falls back to "manual" template if strategy has no custom checklist.

#### `submit_checklist(db, trade_entry_id, responses, conviction, conviction_rationale, emotional_state, entering_for_right_reasons, deviating, deviation_reason) -> PreTradeCheck`

Validates and stores the pre-trade checklist:

1. Verify TradeEntry exists and is "open"
2. Verify no existing checklist for this trade
3. Validate `conviction_level` is 1-5
4. Require `conviction_rationale` is non-empty (minimum 10 characters)
5. If `deviating_from_plan` is True, require `deviation_reason`
6. Auto-populate market context from Market Pulse
7. Store and return

**The conviction rationale requirement is critical.** Forces the trader to articulate WHY, not just rate confidence on a scale. "I'm a 4 because the daily chart shows textbook EMA pullback with sector tailwind and volume drying up" is useful data. "I'm a 4" is not.

#### `check_red_flags(checklist: PreTradeCheck) -> list[str]`

Returns warnings if the checklist reveals process issues:
- `emotional_state` is "fomo" or "revenge" -> "Warning: entering under emotional pressure"
- `entering_for_right_reasons` is False -> "You indicated you may not be entering for the right reasons"
- `deviating_from_plan` is True -> "Deviating from strategy rules — ensure this is deliberate"
- Conviction <= 2 -> "Low conviction — consider whether this trade is worth the risk"
- More than 2 checklist items are False -> "Multiple strategy criteria not met"

These are WARNINGS, not blocks. The system never prevents you from trading. It makes you acknowledge what you're doing.

---

## Service 3: `services/process_analytics.py`

The payoff. Separates process quality from outcome quality.

### Functions

#### `compute_trade_stats(db, filters) -> dict`

Filters: strategy_id, date_range, regime, status (closed only for stats).

Returns:
```python
{
    "total_trades": 45,
    "open_trades": 3,
    "closed_trades": 42,
    "cancelled": 2,

    # Outcome Stats
    "win_rate": 0.55,
    "avg_winner_r": 1.8,
    "avg_loser_r": -0.9,
    "expectancy": 0.585,  # (0.55 * 1.8) + (0.45 * -0.9)
    "total_pnl": 4250.0,
    "avg_hold_days": 7.2,
    "profit_factor": 2.2,  # gross_wins / gross_losses

    # Process Stats
    "avg_process_score": 72.0,
    "process_score_distribution": {"A": 12, "B": 18, "C": 8, "D": 3, "F": 1},
    "avg_entry_grade": "B",
    "avg_management_grade": "B+",
    "avg_exit_grade": "C+",
    "pct_followed_strategy": 0.81,
    "pct_honored_stops": 0.93,
    "avg_emotional_influence": 1.8,

    # Process vs Outcome Matrix (THE key insight)
    "process_outcome_matrix": {
        "good_process_win": 18,    # did it right, won — skill
        "good_process_loss": 8,    # did it right, lost — variance
        "bad_process_win": 5,      # got lucky — leak
        "bad_process_loss": 11,    # predictable result — leak
    },

    # Slippage
    "avg_entry_slippage": 0.12,
    "avg_stop_slippage": -0.08,
}
```

**The Process-Outcome Matrix** is the crown jewel. It cross-references process_score (above/below 65 = good/bad) with trade outcome (profitable/unprofitable). The four quadrants tell you exactly where you stand:
- Good process + Win = skill edge, keep doing this
- Good process + Loss = normal variance, don't change anything
- Bad process + Win = lucky, this will revert — fix the process
- Bad process + Loss = the most expensive quadrant, but also the most fixable

#### `compute_regime_performance(db) -> dict`

P&L and process stats broken down by Market Pulse regime at entry:
```python
{
    "RISK_ON": {"trades": 20, "win_rate": 0.65, "expectancy": 0.82, "avg_process": 75},
    "RISK_OFF": {"trades": 12, "win_rate": 0.33, "expectancy": -0.15, "avg_process": 68},
    "ROTATION": {"trades": 10, "win_rate": 0.50, "expectancy": 0.35, "avg_process": 71},
}
```

This answers: "Am I profitable because I'm good, or because I only traded in a bull market?"

#### `compute_conviction_performance(db) -> dict`

Win rate and expectancy by conviction level (1-5). Tests whether your conviction calibration is accurate — do high-conviction trades actually perform better?

#### `compute_emotional_leakage(db) -> dict`

Compares trades where `emotional_state` was "calm"/"confident" vs "fomo"/"revenge"/"bored". Quantifies how much money emotional trades cost you.

#### `compute_process_trend(db, window=20) -> list`

Rolling 20-trade average of process_score over time. Are you getting more disciplined or less? Returns list of `{"trade_number": N, "rolling_process_score": float, "rolling_win_rate": float}`.

---

## Router: `routers/trades.py`

Prefix: `/api/journal/trades`

### Endpoints

#### `POST /api/journal/trades/enter`

Enter a trade from a Candidate.

```json
{
    "candidate_id": 42,
    "actual_entry": 264.50,
    "actual_size": 95,
    "notes": "Entered on pullback to 8 EMA with volume drying up"
}
```

Returns TradeEntry + checklist template for the strategy.

#### `POST /api/journal/trades/enter-manual`

Enter a trade not from scanner.

```json
{
    "ticker": "NVDA",
    "entry_price": 890.0,
    "stop_loss": 865.0,
    "target_1": 940.0,
    "actual_size": 10,
    "strategy_id": "manual",
    "trade_structure": "stock",
    "notes": "Breakout above consolidation range"
}
```

#### `POST /api/journal/trades/{trade_id}/checklist`

Submit pre-trade checklist.

```json
{
    "responses": {"daily_trend": true, "pullback_to_ema": true, "rs_confirmed": true, "volume_dry": false},
    "conviction_level": 4,
    "conviction_rationale": "Textbook EMA pullback with sector tailwind. Volume not ideal but everything else aligns.",
    "emotional_state": "calm",
    "entering_for_right_reasons": true,
    "deviating_from_plan": false
}
```

Returns PreTradeCheck + any red flag warnings.

#### `PATCH /api/journal/trades/{trade_id}`

Update open trade (stop adjustment, notes).

```json
{
    "actual_stop": 260.0,
    "notes": "Moved stop to breakeven after hitting 1R"
}
```

#### `POST /api/journal/trades/{trade_id}/exit`

Close the trade.

```json
{
    "actual_exit": 278.50,
    "actual_exit_date": "2026-03-15",
    "exit_reason": "target_hit",
    "fees": 2.50,
    "notes": "Hit target 1, clean exit"
}
```

Returns TradeEntry with computed P&L + R-multiple.

#### `POST /api/journal/trades/{trade_id}/review`

Submit post-trade review.

```json
{
    "entry_timing_score": 4,
    "entry_patience_score": 3,
    "entry_notes": "Entered slightly early, should have waited for the doji close",
    "stop_honored": true,
    "stop_moved": true,
    "stop_move_justified": true,
    "added_to_position": false,
    "management_notes": "Trailed stop to breakeven at 1R as planned",
    "exit_timing_score": 5,
    "exit_followed_plan": true,
    "exit_notes": "Clean exit at target",
    "followed_strategy_rules": true,
    "emotional_influence": 1,
    "would_take_again": true,
    "key_lesson": "Waiting for the doji close would have given 0.3R better entry"
}
```

Returns PostTradeReview with computed grades + process score. Also updates TradeEntry.process_score and grade fields.

#### `GET /api/journal/trades`

List trades with filters: status, strategy_id, date range, ticker.

#### `GET /api/journal/trades/{trade_id}`

Full trade detail including checklist + review if completed.

#### `POST /api/journal/trades/{trade_id}/cancel`

Cancel a trade.

---

## Router: `routers/analytics.py`

Prefix: `/api/journal/analytics`

#### `GET /api/journal/analytics/summary`

Overall stats from `compute_trade_stats()`. Accepts query params for filtering.

#### `GET /api/journal/analytics/process-outcome-matrix`

The 2x2 matrix. Returns counts + trade lists for each quadrant.

#### `GET /api/journal/analytics/regime`

Performance by regime from `compute_regime_performance()`.

#### `GET /api/journal/analytics/conviction`

Performance by conviction level.

#### `GET /api/journal/analytics/emotional-leakage`

Emotional impact analysis.

#### `GET /api/journal/analytics/process-trend`

Rolling process quality over time.

---

## UI Panel

The Journal gets its own sidebar tab (like Scanner, Portfolio, Market Pulse).

### Tab 1: Trade Log

Sortable table of all trades:

```
Date     | Ticker | Strategy        | Structure | Entry  | Exit   | R    | P&L    | Process | Status
03/15    | AAPL   | EMA Pullback    | Stock     | 264.50 | 278.50 | +2.1 | +$1330 | 82 (A)  | Closed
03/12    | MSFT   | Trend Following | Bull Call | 415.00 | —      | —    | —      | —       | Open
03/10    | NVDA   | Manual          | Stock     | 890.00 | 865.00 | -1.0 | -$250  | 45 (D)  | Closed
```

Color coding: process score A/B = green, C = yellow, D/F = red. P&L color is separate (green/red). This visual separation reinforces that green P&L with red process is a WARNING, not a success.

### Tab 2: Open Trades

Active trades with:
- Current P&L (live from market data)
- Distance to stop and target (with percentage)
- Days held
- Checklist completion indicator (green check if done, red exclamation if missing)
- "Exit" and "Add Note" buttons

### Tab 3: Process Analytics

Dashboard with:

**Process-Outcome Matrix** (prominent, top of page):
Four quadrant chart. Each quadrant shows count and percentage. Color: top-left green (skill), top-right blue (variance), bottom-left orange (lucky), bottom-right red (leak).

**Headline Stats Row:**
- Win Rate | Expectancy | Avg R | Process Score | Profit Factor

**Process Trend Chart:**
Line chart showing rolling 20-trade process score and rolling win rate on same axis. Ideally both lines trend up and track together.

**Regime Breakdown:**
Bar chart: trades and expectancy by RISK_ON / RISK_OFF / ROTATION.

**Conviction Calibration:**
Table showing win rate and avg R at each conviction level (1-5). If conviction 5 doesn't outperform conviction 3, your calibration needs work.

**Emotional Leakage:**
Simple comparison: P&L from calm/confident trades vs fomo/revenge/bored trades.

### Tab 4: Enter Trade

Form for manual trade entry (non-scanner trades). Fields: ticker, entry, stop, target, size, strategy (dropdown), structure, notes.

---

## Grade Computation

### Entry Grade
```
raw = (entry_timing_score + entry_patience_score) / 2   # 1-5 scale
A = 4.5+, B = 3.5+, C = 2.5+, D = 1.5+, F = below 1.5
```

### Management Grade
```
base = 3.0  # neutral start
if stop_honored: base += 1.0
if stop_moved and stop_move_justified: base += 0.5
if stop_moved and not stop_move_justified: base -= 1.0
if not stop_honored: base -= 2.0
# Same letter scale as entry
```

### Exit Grade
```
raw = exit_timing_score  # 1-5 scale
if exit_followed_plan: raw += 0.5  # bonus for discipline
# Same letter scale
```

### Overall Process Score (0-100)
```
entry_component = (entry_grade_numeric / 5.0) * 30        # 30% weight
management_component = (management_grade_numeric / 5.0) * 35  # 35% weight
exit_component = (exit_grade_numeric / 5.0) * 20          # 20% weight
discipline_component = 15 * (1.0 if followed_strategy_rules else 0.0)  # 15% weight
emotional_penalty = max(0, (emotional_influence - 2) * 5)  # 0-15 point penalty

process_score = entry_component + management_component + exit_component + discipline_component - emotional_penalty
process_score = max(0, min(100, process_score))
```

Management gets the heaviest weight because honoring stops is the single most important discipline in trading. Entry and exit can be refined over time, but moving stops or ignoring them destroys accounts.

---

## Edge Cases

- **No Candidate link**: Manual trades have `candidate_id = None`. All analytics still work since they key off TradeEntry fields.
- **Partial exits**: Handle by allowing multiple exit events (future scope). For now, treat as single exit of full position.
- **Options trades**: `pnl_dollars` computed differently — `(exit_premium - entry_premium) * contracts * 100 - fees`. The lifecycle service checks `trade_structure` and adjusts.
- **Weekend entries**: If entered on weekend, `actual_entry_date` should be the next trading day. UI can default to "today" with override.
- **Missing checklist**: Trade can proceed without checklist (it's discipline, not enforcement), but the UI shows a persistent warning badge.
- **Missing review**: Same — trade closes fine, but analytics exclude unreviewed trades from process scoring. UI shows "Review Pending" badge.
- **Cancelled trades**: Excluded from all performance analytics. Visible in log with "Cancelled" tag.
- **Regime not available**: If Market Pulse hasn't been run, regime fields are null. Analytics handles gracefully.

---

## Scanner Integration

### Modifications to Scanner Module

**Strategy model** (`modules/scanner/models.py`): Add `checklist_template: JSON` field to Strategy model. Nullable, defaults to None. If None, uses the "manual" default checklist.

**Candidate status endpoint** (`modules/scanner/routers/candidates.py`): When status changes to "entered", the journal can optionally auto-create a TradeEntry. But the primary flow is: user clicks "Enter Trade" in the journal UI which calls the journal's enter endpoint with the candidate_id.

---

## Dependencies

No new packages. Uses existing SQLAlchemy, FastAPI, yfinance (for context capture).

---

## Testing Checklist

- [ ] `enter_trade()` creates TradeEntry with context auto-populated from Market Pulse
- [ ] `enter_manual_trade()` works without Candidate link
- [ ] Planned fields are immutable after creation
- [ ] `exit_trade()` computes correct R-multiple using PLANNED stop (not actual)
- [ ] Options trade P&L uses contract multiplier
- [ ] Checklist template loads correctly per strategy
- [ ] Red flags fire for emotional states and deviations
- [ ] `conviction_rationale` enforced as non-empty
- [ ] Post-trade review computes correct grades
- [ ] Process score formula produces 0-100 range
- [ ] Process-Outcome Matrix correctly categorizes trades (process >= 65 = good)
- [ ] Regime performance correctly groups by regime_at_entry
- [ ] Conviction calibration shows meaningful differentiation
- [ ] Cancelled trades excluded from analytics
- [ ] Unreviewed trades excluded from process scoring
- [ ] Trade log shows both P&L color AND process color independently
- [ ] Process trend chart handles < 20 trades (use available window)

---

## Build Order

1. `models.py` — all three models + Strategy checklist_template field
2. `services/trade_lifecycle.py` — enter, exit, cancel, update
3. `services/checklist.py` — template loading, submission, red flags
4. `services/process_analytics.py` — all analytics functions
5. `routers/trades.py` — trade CRUD + lifecycle endpoints
6. `routers/analytics.py` — analytics endpoints
7. `__init__.py` — BaseModule registration
8. UI: Trade log + open trades tabs
9. UI: Process analytics dashboard
10. UI: Enter trade form

---

## What This Does NOT Do (Future Scope)

- Screenshot/chart attachment (would need file storage)
- Partial exits / scaling out (single exit for now)
- Strategy-level P&L attribution (which strategy makes the most money) — partially available via filter, but no dedicated view
- Social/sharing features (export to blog, share with mentor)
- Integration with broker for auto-fill execution data
- Calendar heat map of trading activity
- Risk of ruin calculation based on current stats
