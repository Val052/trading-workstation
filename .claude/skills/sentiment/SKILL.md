---
name: sentiment
description: Internal sentiment and catalyst analysis. Scores news, analyst consensus, and upcoming events on 0-5 scale. Referenced by the analyze skill.
---

# Sentiment & Catalysts — Internal Skill

**Type**: Internal (called by `/analyze`, not directly by user)
**Purpose**: Score news, analyst consensus, and upcoming catalysts on a 0-5 scale

## Analysis Components

### 1. Recent News (Last 2 Weeks)
- Material developments: earnings, guidance, M&A, product launches, regulatory
- Management changes, lawsuits, accounting issues
- Sector-wide news affecting this company
- Source: MCP news tools → web search fallback

### 2. Analyst Consensus
From data-fetcher output:
- Number of buy/hold/sell ratings
- Average price target vs current price (upside/downside %)
- Recent rating changes (upgrades/downgrades in last 30 days)
- Price target revisions (trend up or down)

### 3. Institutional Activity
- Major fund filings if available via web search
- 13F data (quarterly, often delayed — note staleness)
- Insider buying/selling (significant transactions only)

### 4. Event Calendar
- Next earnings date and days until
- Ex-dividend date (if applicable)
- Conference presentations, analyst days
- Product launch dates, regulatory decision dates

### 5. Catalyst Identification
What could move this stock in the next 1-3 months?
- **Positive catalysts**: earnings beats, new products, M&A, share buybacks, index inclusion
- **Negative catalysts**: earnings misses, regulatory risk, competitive threats, macro headwinds
- **Binary events**: FDA decisions, trial results, antitrust rulings

## Scoring Rubric (0-5)

| Score | Meaning |
|-------|---------|
| 5 | Strong positive: recent upgrades, beats, positive catalysts ahead, institutional accumulation |
| 4 | Moderately positive: mostly bullish sentiment, some catalysts |
| 3 | Neutral: no major catalysts either way, mixed analyst views |
| 2 | Moderately negative: some headwinds, downgrades, near-term risks |
| 1 | Negative: significant headwinds, downgrades, regulatory risks, poor sentiment |
| 0 | Unable to assess / no data |

## Rules
- Do not fabricate analyst ratings or news. If unavailable, score 3 (neutral) and note data gap.
- Distinguish between noise and signal — a single analyst upgrade is less meaningful than a consensus shift.
- Earnings within 2 weeks is always a catalyst worth noting (risk of gap up/down).

## Output Format

```
SENTIMENT SCORE: X.X / 5

News: [summary of material developments]
Analysts: XX buy / XX hold / XX sell — avg target $XXX (XX% upside)
Events: Next earnings [DATE], [other events]
Catalysts: [positive and negative identified]
```
