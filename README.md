# stock-red-flags

[![tests](https://github.com/vasimmistry-dev/stock-red-flags/actions/workflows/tests.yml/badge.svg)](https://github.com/vasimmistry-dev/stock-red-flags/actions/workflows/tests.yml)
![python](https://img.shields.io/badge/python-3.9%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

Transparent **fundamental red-flag and quality checks** for listed companies, built from yearly financial statements. Pure Python with zero dependencies.

- **11 red-flag checks.** Each flag has an id, a severity (`low` / `medium` / `high`), a plain-English explanation, and the exact numbers that triggered it.
- **Piotroski F-score.** All 9 criteria, with a pass/fail breakdown.
- **Altman Z-score.** The original 1968 model, with its limitations stated.
- **ROE, ROCE, D/E, P/E, interest coverage** and other ratios.
- **A screener-style filter.** Write conditions like `roe > 15` and `de < 0.5`.

The checks are tuned for Indian listed companies: promoter holding and pledge data, plus an `is_financial` switch for banks and NBFCs. They work for any market if you supply the numbers. This library was extracted from the logic behind features like the *red flags* analysis and screener filters on [TickerKhoj](https://tickerkhoj.com), a free Indian stock analysis site. It is published on its own so every rule can be read, questioned and tested.

## Why

A score without an explanation is hard to trust. Here every flag shows *why* it fired:

```
[MEDIUM] Receivables growing much faster than revenue
         Receivables grew 50.0% while revenue grew 9.1% (gap 40.9%, threshold 20.0%).
         Debtor days went from 66 to 91 days.
```

Every threshold lives in a single `Thresholds` dataclass, so you can change it.

## Install

```bash
pip install git+https://github.com/vasimmistry-dev/stock-red-flags.git
# or, from a clone:
pip install -e ".[test]"
```

## CLI

```bash
red-flags check examples/company.json            # human-readable report
red-flags check examples/company.json --json     # machine-readable
red-flags check companies.json --fail-on high    # exit code 1 if any high-severity flag fires
red-flags screen examples/companies.json --roe-min 15 --de-max 0.5
red-flags screen companies.json --where "interest_coverage > 5" --where "pledge < 1"
```

`--roe-min 15` means `roe >= 15`. All companies in the `examples/` folder are **fictional**.

```
$ red-flags check examples/company.json
========================================================================
Sample Fabrics Ltd (SAMPLEFAB) - FY2025
ROE 15.3%   ROCE 14.4%
Piotroski F-score: 4 (out of 9 criteria with data; asset basis: beginning)
   PASS  roa_positive
   PASS  cfo_positive
   PASS  roa_improving
   fail  accruals
   ...
Altman Z-score: 2.84 (grey zone)
Red flags (6):
  [HIGH  ] High promoter pledge
           28.0% of promoter shares are pledged (threshold 25%). ...
  [MEDIUM] Profit growing but cash flow weak
           Over 2023-2025 net profit grew, but operating cash flow covered only 45.6% of cumulative profit ...
  ...

$ red-flags screen examples/companies.json --roe-min 15 --de-max 0.5
Conditions: roe >= 15.0 AND de <= 0.5
2 of 5 companies match

company                 roe       roce         de         pe market_cap     fscore high_flags
ALPHA                 25.66      34.56       0.02      48.24   16400.00       9.00       0.00
EPSILON               17.45      20.97       0.27      54.05   10000.00       5.00       0.00
```

## Python

```python
from stock_red_flags import load_companies, check_company, piotroski, altman_z, roe, screen, Thresholds

company = load_companies("examples/company.json")[0]

for f in check_company(company):
    print(f.severity, f.id, f.evidence)

fs = piotroski(company)
print(fs.score, "/", fs.evaluated)
for c in fs.criteria:
    print(c.name, c.passed, c.values)

z = altman_z(company)
print(z.z, z.zone, z.components)

# stricter limits
check_company(company, Thresholds(de_max=0.5, pledge_max_pct=10))

# screener
for r in screen(load_companies("examples/companies.json"), ["roe > 15", "de < 0.5", "fscore >= 6"]):
    print(r.company.symbol, r.metrics["roe"])
```

## Input schema

You can supply JSON or CSV. In JSON, the file can be a single company object, a list of them, or `{"companies": [...]}`:

```json
{
  "name": "Sample Fabrics Ltd",
  "symbol": "SAMPLEFAB",
  "is_financial": false,
  "years": [
    {"year": 2024, "revenue": 1100, "net_profit": 95, "operating_cash_flow": 40, "...": "..."},
    {"year": 2025, "revenue": 1200, "net_profit": 110, "operating_cash_flow": 20, "...": "..."}
  ]
}
```

In CSV, use one row per company-year with a `symbol` (or `name`) column. The optional `is_financial` column takes `true` or `false`. See [`examples/companies.csv`](examples/companies.csv).

| field | meaning | used by |
|---|---|---|
| `year` | fiscal year (int, **required**) | all |
| `revenue` | revenue from operations | receivables/inventory flags, F-score, Z, growth |
| `net_profit` | profit after tax (PAT) | CFO/PAT, losses, ROE, F-score, P/E |
| `operating_cash_flow` | cash flow from operations (CFO) | CFO flags, F-score |
| `total_debt` | borrowings (short + long term) | D/E, debt flag, ROCE, F-score |
| `equity` | shareholders' funds (net worth) | D/E, ROE, ROCE |
| `interest_expense` | finance costs | interest coverage |
| `ebit` | earnings before interest and tax | coverage, ROCE, Z |
| `receivables` | trade receivables | receivables flag |
| `inventory` | inventories | inventory flag |
| `total_assets` | balance-sheet total | F-score, Z |
| `current_assets`, `current_liabilities` | | current ratio, F-score, Z |
| `shares_outstanding` | share count | dilution, F-score, market value |
| `promoter_holding_pct` | promoter + group holding, % (0-100) | promoter flag |
| `promoter_pledged_pct` | % of promoter shares pledged (0-100) | pledge flags |
| `price` | share price at year end *(optional)* | market value, P/E, Z |
| `gross_profit` | *(optional)* revenue minus cost of materials/goods | F-score criterion 8 |
| `retained_earnings` | *(optional)* reserves & surplus / other equity | Z (X2) |
| `total_liabilities` | *(optional)* defaults to `total_assets - equity` | Z (X4) |
| `market_cap` | *(optional)* overrides `price * shares_outstanding` | P/E, Z, screen |

**Units.** Use one money unit for each company (for example ₹ crore). If you supply `price`, give `shares_outstanding` in a unit where `price * shares` comes out in that money unit: for figures in ₹ crore, enter the share count in crore. A missing field never crashes a check. The check, or the single criterion that needs the field, is simply skipped.

## Red-flag rules

"Latest" means the most recent year in the file, and "previous" means the year before it. Growth is `cur / prev - 1`, and it is computed only when the previous value is positive.

| id | severity | fires when |
|---|---|---|
| `cfo_weak_vs_profit` | medium; high if ratio < 0.3 | over the last 3 years: cumulative PAT > 0, latest PAT > PAT two years earlier (profit growing), and `sum(CFO) / sum(PAT) < 0.7`. *Skipped for financials* |
| `receivables_outpacing_revenue` | medium; high if gap > 50 pp | `receivables growth - revenue growth > 20 pp`, and receivables are at least 5% of revenue (materiality) |
| `inventory_outpacing_revenue` | medium; high if gap > 50 pp | same rule, applied to inventory |
| `high_debt_to_equity` | medium; high if D/E > 2 | `total_debt / equity > 1`. *Skipped when `is_financial` is true* |
| `negative_equity` | high | `equity <= 0` |
| `low_interest_coverage` | medium; high if < 1x | `ebit / interest_expense < 2` and interest > 0. *Skipped for financials* |
| `rising_debt_falling_profit` | medium; high if PAT < 0 | debt up more than 10% YoY **and** PAT below the previous year. *Skipped for financials* |
| `promoter_pledge_high` | high | pledged share of promoter holding > 25% |
| `promoter_pledge_rising` | low if the new level is ≤ 10%, else medium | pledge up by at least 5 percentage points YoY |
| `promoter_holding_falling` | medium; high if > 10 pp | promoter holding down by more than 5 percentage points YoY |
| `equity_dilution` | medium; high if > 25% | shares outstanding up more than 10% YoY |
| `repeated_losses` | medium; high if 3 of 3 | net loss in at least 2 of the last 3 years |
| `negative_cfo` | medium; high if negative in 2+ of the last 3 years | latest CFO < 0. *Skipped for financials* |

For banks, NBFCs and insurers, lending and deposits pass through operating cash flow and borrowings. That makes the CFO, leverage and coverage checks misleading for them, so those checks are skipped when `is_financial` is true.

## Quality scores

### Piotroski F-score (Piotroski, 2000)

The score is one point per criterion, comparing the scored year *t* with *t-1*.

| # | criterion | rule used here |
|---|---|---|
| 1 | `roa_positive` | `net_profit / assets > 0` |
| 2 | `cfo_positive` | `operating_cash_flow > 0` |
| 3 | `roa_improving` | ROA(t) > ROA(t-1) |
| 4 | `accruals` | CFO > net profit (equivalent to CFO/assets > ROA, since both use the same denominator) |
| 5 | `leverage_falling` | `total_debt / total_assets` lower than last year. Debt-free in both years also passes |
| 6 | `current_ratio_improving` | current ratio higher than last year |
| 7 | `no_dilution` | shares outstanding not higher than last year |
| 8 | `gross_margin_improving` | `gross_profit / revenue` higher than last year (needs `gross_profit`) |
| 9 | `asset_turnover_improving` | `revenue / assets` higher than last year |

- **Asset basis:** "assets" means *beginning-of-year* total assets, as in the paper, when a year *t-2* exists. With only two years, both years use end-of-year assets so the comparison stays like-for-like. The result reports which basis was used (`asset_basis`).
- **Deviations from the paper:** criterion 5 uses total debt and end-of-year assets, while the paper uses long-term debt and average assets.
- **Missing data:** a criterion without data gets `passed=None`. Read `score` together with `evaluated`, the number of criteria that had data.

### Altman Z-score (original 1968 model)

`Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5`

| term | ratio |
|---|---|
| X1 | working capital / total assets |
| X2 | retained earnings / total assets |
| X3 | EBIT / total assets |
| X4 | market value of equity / total liabilities |
| X5 | revenue / total assets |

The zones are **safe** above 2.99, **grey** from 1.81 to 2.99, and **distress** below 1.81.

> **Limitations:** the model was fitted on US listed *manufacturing* firms in the 1960s. It is not meaningful for banks, NBFCs or insurers, which get a warning when `is_financial` is true. It is also weak for asset-light services firms. At high Indian market valuations, X4 can dominate the score: a richly valued loss-maker can land in the "safe" zone, as the fictional `DELTA` example shows. Read the components, not just the zone.

### Ratios

- **ROE** = net profit / average(opening, closing) equity × 100. If there is no previous year, closing equity is used.
- **ROCE** = EBIT / average(equity + total debt) × 100.
- **P/E** = market value / net profit. It is `None` for loss-makers.

### Screener metrics

The metrics available to `screen` are `roe`, `roce`, `de`, `pe`, `market_cap`, `interest_coverage`, `current_ratio`, `sales_growth`, `profit_growth`, `promoter_holding`, `pledge`, `fscore`, `zscore`, `red_flags` and `high_flags`. Conditions use `>`, `>=`, `<`, `<=`, `==` or `!=`. If a company's metric is missing, the company **fails** that condition. For example, a loss-maker never passes `pe < 20`.

## Limitations

- **The data is only as good as your input.** This library does not fetch data. Check annual reports and exchange filings yourself.
- **Simple thresholds.** The thresholds are rules of thumb, not universal truths. Sector context matters: high receivables are normal in some businesses, and a seasonal inventory build is not a fraud signal.
- **Annual data only.** Quarterly swings and restatements are not handled.
- **Corporate actions.** Bonus issues and splits will trigger `equity_dilution` unless the share counts are adjusted first.
- **A flag is a question, not a verdict.** Use flags to decide what to read next in the annual report.

## Development

```bash
pip install -e ".[test]"
pytest -q
```

The tests check that each flag fires and that it stays quiet just inside its threshold. They also compare F-score and Z-score arithmetic against values computed by hand.

## Disclaimer

This project is for **educational and research purposes only**. It is **not investment advice**, a credit rating or a recommendation to buy or sell any security. A company with no flags can still be a bad investment, and a flagged company may have a good explanation. This project is **not affiliated with, endorsed by or connected to the National Stock Exchange of India (NSE)**, BSE or SEBI. The example companies are fictional. Do your own research or consult a SEBI-registered adviser.

## License

MIT © 2026 Vasim Mistry
