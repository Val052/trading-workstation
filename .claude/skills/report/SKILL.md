# Report Compilation — Internal Skill

**Type**: Internal (called by `/analyze` after all other skills complete)
**Purpose**: Compile all skill outputs into a structured research report

## Report Template

Format every analysis report exactly as follows:

```
═══════════════════════════════════════════════════════════
  RESEARCH REPORT: [TICKER] — [COMPANY NAME]
  Date: [DATE]  |  Analyst: Trading Workstation AI
═══════════════════════════════════════════════════════════

RECOMMENDATION: [STRONG BUY / BUY / HOLD / SELL / STRONG SELL]
COMPOSITE SCORE: [X.XX / 10]

PRICE: $XXX.XX  |  52W RANGE: $XXX - $XXX  |  MARKET CAP: $XXXB

── EXECUTIVE SUMMARY ─────────────────────────────────────
[2-3 sentence thesis. What is the core reason to buy, hold, or sell?
Include the single most important factor driving the recommendation.]

── SCORING BREAKDOWN ─────────────────────────────────────
Technical  (30%): X.X/10  — [one-line summary]
Fundamental(40%): X.X/10  — [one-line summary]
Sentiment  (15%): X.X/5   — [one-line summary]
Risk       (15%): X.X/5   — [one-line summary]

Weighted Composite: (tech × 0.30) + (fund × 0.40) + (sent/5 × 10 × 0.15) + (risk/5 × 10 × 0.15) = X.XX

── TECHNICAL ANALYSIS ────────────────────────────────────
[Full output from technical skill]

── FUNDAMENTAL ANALYSIS ──────────────────────────────────
[Full output from fundamental skill]

── SENTIMENT & CATALYSTS ─────────────────────────────────
[Full output from sentiment skill]

── RISK ASSESSMENT ───────────────────────────────────────
[Full output from risk skill]

── TRADE PARAMETERS ──────────────────────────────────────
Entry Zone:    $XXX.XX - $XXX.XX
Stop Loss:     $XXX.XX (X.X% risk from entry)
Target 1 (1R): $XXX.XX
Target 2 (2R): $XXX.XX
Target 3 (3R): $XXX.XX
Position Size: XXX shares ($XX,XXX / XX% of portfolio)
Max Risk:      $XXX (X.X% of portfolio)
R/R Ratio:     X.X:1

── STRATEGY CONVERGENCE ──────────────────────────────────
[If ticker appeared in workstation scan results, list:
 - Which strategies triggered
 - When (scan dates)
 - Key signal data from each
 - Whether it was a full hit or near-miss
If no scan results: "No recent scanner activity for this ticker."]

── PREVIOUS ANALYSIS ─────────────────────────────────────
[If previously analyzed (check memory/decisions/analysis-log.md):
 - Last analysis date and score
 - Previous recommendation
 - Key thesis at that time
 - What has changed since then (price, fundamentals, sentiment)
 - Score delta and direction
If first analysis: "First analysis — no prior data."]

── DATA SOURCES & TIMESTAMPS ─────────────────────────────
[List every data source used and when the data was retrieved]
- Price data: [source] as of [timestamp]
- Fundamentals: [source] as of [timestamp]
- Analyst data: [source] as of [timestamp]
- News: [source] as of [timestamp]

⚠️  DISCLAIMER: Research tool output only. Not financial advice.
    All data should be independently verified before trading decisions.
═══════════════════════════════════════════════════════════
```

## Post-Report Actions

After generating the report:

1. **Save to memory**: Write the full report to `memory/reports/[TICKER]_[YYYY-MM-DD].md`

2. **Update analysis log**: Append to `memory/decisions/analysis-log.md`:
   ```
   | [DATE] | [TICKER] | [SCORE] | [RECOMMENDATION] | [one-line thesis] | [mode] | reports/[TICKER]_[DATE].md |
   ```

3. **Offer pipeline actions** (if BUY or STRONG BUY):
   - "Add to watchlist?" → update `memory/decisions/current-positions.md` watchlist section
   - "Add to candidates in web app?" → insert into SQLite candidates table:
     ```python
     python3 -c "
     from app.database import SessionLocal
     from app.models import Candidate
     db = SessionLocal()
     c = Candidate(
         scan_result_id=None,  # manual entry
         ticker='TICKER',
         entry_price=ENTRY,
         stop_loss=STOP,
         target_1=TARGET,
         risk_per_share=RISK,
         reward_per_share=REWARD,
         r_multiple=RMULT,
         position_size=SIZE,
         status='watching'
     )
     db.add(c)
     db.commit()
     print(f'Added {c.ticker} to candidates (id={c.id})')
     db.close()
     "
     ```

## Score-to-Recommendation Mapping

| Composite Score | Recommendation |
|----------------|----------------|
| 8.5 - 10.0 | STRONG BUY |
| 7.0 - 8.4 | BUY |
| 5.0 - 6.9 | HOLD |
| 3.0 - 4.9 | SELL |
| 0.0 - 2.9 | STRONG SELL |
