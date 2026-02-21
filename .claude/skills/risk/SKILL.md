---
name: risk
description: Internal risk assessment engine. Calculates volatility, stop-loss, position sizing (2% rule), R-multiples, and concentration checks on 0-5 scale. Referenced by the analyze skill.
---

# Risk Assessment & Position Sizing — Internal Skill

**Type**: Internal (called by `/analyze`, not directly by user)
**Purpose**: Calculate risk metrics, position sizing, and concentration checks. Score 0-5.

## Analysis Components

### 1. Volatility Profile
- **Beta**: vs S&P 500 (from data-fetcher)
- **ATR (14)**: absolute and as % of price
- **30-day realized volatility**: annualized standard deviation of daily returns
- **Classification**: Low (<1.0 beta, <2% daily ATR), Medium (1.0-1.5 beta), High (>1.5 beta, >3% daily ATR)

### 2. Stop-Loss Placement
Two methods, take the wider one:
1. **ATR-based**: Entry - (2 × ATR) for longs
2. **Technical level**: Below the nearest significant support (swing low, key MA, AVWAP)

Always round to a clean price level. The stop must make structural sense — not just a mathematical distance.

### 3. Position Sizing

Read account configuration:
```python
python3 -c "
from app.database import SessionLocal
from app.models import AccountConfig
db = SessionLocal()
a = db.query(AccountConfig).order_by(AccountConfig.id.desc()).first()
if a: print(f'Size: {a.account_size}, Risk: {a.risk_per_trade}, Max Pos: {a.max_positions}')
else: print('Defaults: 10000, 0.005, 5')
db.close()
"
```

Also read `memory/decisions/current-positions.md` for:
- Current number of open positions
- Current sector exposure
- Cash remaining

**Sizing formula**:
```
risk_per_share = entry_price - stop_loss
max_dollar_risk = account_size × 0.02          # hard cap: 2% per trade
position_size = floor(max_dollar_risk / risk_per_share)
position_value = position_size × entry_price
```

**Constraints** (all must pass):
1. Dollar risk ≤ 2% of account
2. Position value ≤ 10% of account
3. Not exceeding max_positions count
4. If macro outlook is Bearish (from `memory/economic-views/market-outlook.md`): reduce size by 30%
5. If VIX > 30: reduce size by 50%

### 4. R-Multiple Targets
From the chosen entry and stop:
- **1R**: entry + risk_per_share (minimum target for any trade)
- **2R**: entry + 2 × risk_per_share (standard swing target)
- **3R**: entry + 3 × risk_per_share (extended target for strong setups)

### 5. Kelly Criterion (Informational Only)
```
Kelly % = W - (1-W)/R
where:
  W = estimated win rate (use 0.50 if no historical data)
  R = average win / average loss (use the R-multiple as proxy)
```
Show the math. Note this is theoretical — real position sizing uses the 2% rule above, not Kelly.

### 6. Concentration Check
If holding or considering positions in the same sector:
- Flag if total sector exposure would exceed 25% of portfolio
- Flag if this would be the 3rd+ position in the same sector
- Note correlation risk explicitly

### 7. Risk/Reward Assessment
- **R/R ratio**: reward_per_share / risk_per_share (minimum 2:1 for consideration, 3:1 preferred)
- If R/R < 2:1, note that the setup does not meet minimum criteria regardless of other scores

## Scoring Rubric (0-5)

| Score | Meaning |
|-------|---------|
| 5 | Excellent: low volatility, clear stop, R/R >3:1, no concentration issues, sizing comfortable |
| 4 | Good: moderate volatility, defined stop, R/R >2:1, acceptable sizing |
| 3 | Acceptable: manageable risk, R/R ~2:1, some concerns |
| 2 | Elevated: high volatility, wide stop, R/R <2:1, or concentration risk |
| 1 | Poor: very high risk, unclear levels, R/R <1.5:1, overconcentrated |
| 0 | Unacceptable: cannot define risk, skip this trade |

## Output Format

```
RISK SCORE: X.X / 5

Volatility: [Low/Medium/High] — Beta X.X, ATR $X.XX (X.X%), 30d vol XX%
Stop Loss: $XXX.XX ([method]: [reasoning])
Position Size: XXX shares ($XX,XXX / XX% of portfolio)
Risk: $XXX (X.X% of account)
R/R Ratio: X.X:1
Targets: 1R=$XXX, 2R=$XXX, 3R=$XXX
Kelly: XX% (informational)
Concentration: [OK / WARNING: reason]
Macro Adjustment: [None / -30% bearish / -50% high VIX]
```
