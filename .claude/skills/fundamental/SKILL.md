---
name: fundamental
description: Internal fundamental analysis engine. Scores valuation, quality, growth, and financial health (Piotroski, Altman Z) on 0-10 scale. Referenced by the analyze skill.
---

# Fundamental Analysis — Internal Skill

**Type**: Internal (called by `/analyze`, not directly by user)
**Purpose**: Score a ticker's fundamental quality on a 0-10 scale

## Analysis Components

### 1. Valuation (35% of fundamental score)

| Metric | Cheap | Fair | Expensive |
|--------|-------|------|-----------|
| P/E (trailing) | <15 | 15-25 | >25 |
| P/E (forward) | <12 | 12-20 | >20 |
| P/B | <1.5 | 1.5-3.0 | >3.0 |
| P/S | <2.0 | 2.0-5.0 | >5.0 |
| EV/EBITDA | <10 | 10-15 | >15 |
| PEG | <1.0 | 1.0-2.0 | >2.0 |

**Context matters**: Always compare to sector median. A tech stock at 25x P/E may be fairly valued; a utility at 25x is expensive. Use the sector and industry from data-fetcher.

### 2. Quality & Profitability (35% of fundamental score)

| Metric | Excellent | Good | Poor |
|--------|-----------|------|------|
| Gross Margin | >50% | 30-50% | <30% |
| Operating Margin | >20% | 10-20% | <10% |
| Net Margin | >15% | 5-15% | <5% |
| ROE | >20% | 10-20% | <10% |
| ROA | >10% | 5-10% | <5% |
| ROIC | >15% | 8-15% | <8% |

### 3. Growth (20% of fundamental score)

| Metric | Strong | Moderate | Weak |
|--------|--------|----------|------|
| Revenue Growth (YoY) | >20% | 5-20% | <5% |
| Earnings Growth (YoY) | >25% | 5-25% | <5% |
| FCF Growth | >15% | 0-15% | Negative |

### 4. Financial Health (10% of fundamental score)

#### Piotroski F-Score (0-9)
Calculate all 9 criteria:
1. **Profitability** (4 points):
   - Net income positive: +1
   - Operating cash flow positive: +1
   - ROA increasing YoY: +1
   - Cash flow from operations > net income (accruals): +1
2. **Leverage** (3 points):
   - Debt-to-assets decreasing YoY: +1
   - Current ratio increasing YoY: +1
   - No new shares issued: +1
3. **Efficiency** (2 points):
   - Gross margin increasing YoY: +1
   - Asset turnover increasing YoY: +1

Score: 7-9 = Strong, 4-6 = Moderate, 0-3 = Weak

#### Altman Z-Score (non-financial companies only)
Z = 1.2A + 1.4B + 3.3C + 0.6D + 1.0E
- A = Working Capital / Total Assets
- B = Retained Earnings / Total Assets
- C = EBIT / Total Assets
- D = Market Value of Equity / Total Liabilities
- E = Revenue / Total Assets

Score: >2.99 = Safe, 1.81-2.99 = Grey Zone, <1.81 = Distress

#### Other health metrics
- Current ratio (>1.5 healthy)
- Quick ratio (>1.0 healthy)
- Debt-to-equity (<1.0 preferred, sector-dependent)
- Interest coverage (>5x comfortable)

### 5. Cash Flow Quality
- FCF yield: FCF / Market Cap (>5% attractive)
- Capex-to-revenue ratio (sector-dependent)
- FCF conversion: FCF / Net Income (>80% = high quality earnings)

### 6. Quality Flags
Note any red or green flags:
- **Red**: Declining margins, rising debt, negative FCF, earnings quality concerns
- **Green**: Margin expansion, buybacks, dividend growth, insider buying

## Scoring Rubric (0-10)

| Score | Meaning |
|-------|---------|
| 9-10 | Exceptional: cheap valuation, high quality, strong growth, fortress balance sheet |
| 7-8 | Strong: good fundamentals, reasonable valuation, growing |
| 5-6 | Average: fairly valued, stable but unexceptional |
| 3-4 | Below average: expensive for quality, declining metrics |
| 1-2 | Poor: overvalued, deteriorating fundamentals, financial stress |
| 0 | No data / unable to assess |

**Important**: A cheap stock with declining fundamentals should not score above 5. An expensive stock with exceptional growth and quality can score 6-7 but not higher unless the valuation is justified by growth trajectory.

## Output Format

```
FUNDAMENTAL SCORE: X.X / 10

Valuation: [Cheap/Fair/Expensive] — P/E XX, EV/EBITDA XX, PEG X.X
Quality: [Strong/Average/Weak] — ROE XX%, margins XX%
Growth: [Strong/Moderate/Weak] — Revenue +XX%, Earnings +XX%
Health: Piotroski X/9, Z-Score X.XX, D/E X.X
FCF: Yield X.X%, conversion XX%
Flags: [any red or green flags]
```
