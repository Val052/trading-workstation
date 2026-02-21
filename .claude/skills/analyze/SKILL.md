# /analyze — Lead Orchestrator

**Type**: User-facing command
**Usage**: `/analyze [TICKER] [mode]`
**Modes**: `full` (default), `quick`, `update`

## Purpose

Deep-dive research report on a single security. Orchestrates all internal skills, computes a weighted composite score, and produces a formatted research report with actionable trade parameters.

## Execution Flow

### Phase 0: Memory Check
Before any data fetching, read:
1. `memory/decisions/analysis-log.md` — has this ticker been analyzed before? When? What was the score?
2. `memory/decisions/current-positions.md` — do we already hold this? What's our exposure?
3. `memory/economic-views/market-outlook.md` — what's the current macro stance? Any bearish adjustments needed?

### Phase 1: Data Acquisition
Delegate to the `data-fetcher` skill:
- Fetch quote, financials, technicals, analyst data, earnings, news
- Use MCP tools first, yfinance fallback, web search for qualitative
- Timestamp all data points

### Phase 2: Technical Analysis
Delegate to the `technical` skill:
- Trend, momentum, volume, levels, patterns
- Cross-reference with workstation scan results (EMA Pullback, AVWAP, Sector Rotation)
- Output: technical score (0-10)

### Phase 3: Fundamental Analysis
Delegate to the `fundamental` skill:
- Valuation, quality, growth, financial health (Piotroski, Altman Z)
- Compare to sector peers
- Output: fundamental score (0-10)

### Phase 4: Sentiment & Catalysts
Delegate to the `sentiment` skill:
- Recent news, analyst consensus, event calendar, catalyst identification
- Output: sentiment score (0-5)

**Quick mode**: Skip deep sentiment analysis. Use analyst consensus data from yfinance only. Default to 3/5 if unavailable.

### Phase 5: Risk Assessment
Delegate to the `risk` skill:
- Volatility profiling, stop-loss placement, position sizing
- Concentration check against current portfolio
- Macro adjustment if bearish outlook
- Output: risk score (0-5)

### Phase 6: Composite Scoring

Calculate the weighted composite:

```
composite = (technical_score × 0.30)
          + (fundamental_score × 0.40)
          + ((sentiment_score / 5) × 10 × 0.15)
          + ((risk_score / 5) × 10 × 0.15)
```

This normalizes sentiment (0-5) and risk (0-5) to the 0-10 scale before weighting.

Map to recommendation:
| Score | Recommendation |
|-------|----------------|
| 8.5+ | STRONG BUY |
| 7.0 - 8.4 | BUY |
| 5.0 - 6.9 | HOLD |
| 3.0 - 4.9 | SELL |
| < 3.0 | STRONG SELL |

### Phase 7: Report Generation
Delegate to the `report` skill:
- Compile all outputs into the standard report format
- Include trade parameters, strategy convergence, previous analysis comparison
- Save report to `memory/reports/`
- Update `memory/decisions/analysis-log.md`

### Phase 8: Pipeline Offers
If recommendation is BUY or STRONG BUY:
- Offer to add to watchlist (`memory/decisions/current-positions.md`)
- Offer to add to web app candidates (SQLite `candidates` table)

## Mode Details

### `full` (default)
Run all phases completely. Full sentiment deep-dive, comprehensive fundamental analysis, complete report.

### `quick`
Streamlined version:
- Technical + key fundamentals only
- Skip sentiment deep-dive (use analyst consensus from yfinance, default sentiment to 3/5 if unavailable)
- Shorter report format (skip detailed fundamental breakdown, just show key metrics)
- Still computes composite score and recommendation

### `update`
Re-analyze a previously analyzed ticker:
- Read the previous analysis from memory
- Run full analysis
- Show comparative delta: score change, price change, what shifted
- Highlight any thesis changes
- Note if recommendation changed

## Scoring Transparency

The scoring framework is deterministic and auditable:

**Technical (30%)**: Based on trend alignment, momentum readings, volume confirmation, and level structure. Exact rubric in `.claude/skills/technical/SKILL.md`.

**Fundamental (40%)**: Weighted sub-scores — valuation (35%), quality (35%), growth (20%), health (10%). Each sub-component has explicit thresholds. Exact rubric in `.claude/skills/fundamental/SKILL.md`.

**Sentiment (15%)**: Based on analyst consensus, recent catalysts, event calendar. Scale 0-5, normalized to 0-10 for composite. Exact rubric in `.claude/skills/sentiment/SKILL.md`.

**Risk (15%)**: Based on volatility profile, R/R ratio, position sizing feasibility, concentration. Scale 0-5, normalized to 0-10 for composite. Exact rubric in `.claude/skills/risk/SKILL.md`.

No black boxes. Every score should have a clear justification traceable to the rubric.
