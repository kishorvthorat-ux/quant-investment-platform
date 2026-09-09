# Quant Investment Platform — Backtesting Model

## MVP Backtest Objective

The MVP backtest evaluates the complete path:

`Features → Configured Scores → Rankings → Weekly Signals → Next-Day Entry → Hold Until Next Signal → Turnover → Transaction Costs → Net Returns → Performance Metrics`

The purpose of the baseline backtest is to validate strategy mechanics and establish a reproducible reference point before factor optimization.

## Execution Model

For `M_RD_504010_V2` configuration `2`:

- Signals are generated weekly using the last available trading day of each calendar week.
- Portfolio entry occurs on the next available trading day.
- The portfolio contains the top 2 ranked securities.
- Each position receives 50% target weight.
- Positions are held until the next weekly signal.
- There is no fixed holding-period exit.
- Turnover is generated only when the new signal changes target weights.
- Unchanged holdings produce zero turnover during the holding period.

The final available signal may continue to hold through available subsequent trading dates when no later signal exists.

## Turnover and Transaction Costs

Portfolio turnover is calculated from absolute target-weight changes between consecutive position dates and divided by two.

For the top-2 / 50%-50% portfolio:

- Initial deployment from zero can produce 0.50 portfolio turnover.
- One 50% position change produces 0.50 turnover.
- Both positions changing can produce 1.00 turnover.
- Unchanged holdings produce 0.00 turnover.

Transaction costs are applied to turnover to derive net returns. The current baseline uses the transaction-cost framework available to the MVP pipeline; further propagation of configurable costs through all downstream models remains a known architecture item.

## Baseline Performance

Current V2 breadth comparison after official NSE calendar integration:

| Configuration | Breadth | Gross CAGR | Net CAGR | Net Sharpe | Net Max DD | Total Turnover | Transaction Cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| Config 2 | Top-2 | 18.9588% | 12.5855% | 0.7514 | -27.7816% | 183.5000 | 36.7000% |
| Config 3 | Top-4 | 21.2889% | 15.7911% | 1.0099 | -25.7469% | 154.5000 | 30.9000% |
| Config 4 | Top-5 | 23.0550% | 18.0002% | 1.1628 | -26.8856% | 139.7000 | 27.9400% |
| Config 5 | Top-6 | 19.5725% | 14.8902% | 1.0215 | -25.4254% | 133.0000 | 26.6000% |

The official NSE trading calendar is now authoritative for trading-day determination. Yahoo Finance remains the market-price source. The calendar integration changes the reproducibility foundation but does not alter the weekly signal definition.

These figures are research/backtest results, not evidence of guaranteed future profitability.

 a **baseline research result, not a claim of production profitability**.

## Year-by-Year Net Results

| Year | Net return | Volatility | Sharpe | Max daily loss | Max daily gain | Turnover |
|---|---:|---:|---:|---:|---:|---:|
| 2020 | 24.69% | 35.36% | 0.97 | -10.70% | 11.63% | 28.50 |
| 2021 | 63.55% | 27.46% | 2.45 | -4.01% | 5.69% | 29.50 |
| 2022 | 2.74% | 22.54% | 0.27 | -4.24% | 5.21% | 27.00 |
| 2023 | 17.64% | 15.22% | 1.47 | -2.80% | 2.74% | 27.00 |
| 2024 | -12.60% | 24.48% | -0.59 | -13.19% | 4.40% | 29.50 |
| 2025 | 0.51% | 18.48% | 0.13 | -4.33% | 5.56% | 26.50 |
| 2026 YTD | 1.79% | 19.54% | 0.27 | -5.19% | 4.36% | 17.00 |

## Interpretation Boundary

The baseline is technically promising but not yet proven as a robust trading strategy.

The historical results show strong performance in 2020, 2021 and 2023, but weak performance in 2022, 2024, 2025 and 2026 YTD. In particular, 2024 is a significant weak period.

Factor optimization must therefore evaluate more than CAGR. Future experiments should consider:

- CAGR / total return
- Sharpe and risk-adjusted return
- maximum drawdown
- year-by-year consistency
- turnover and transaction costs
- robustness across market regimes

Optimization must not mutate the baseline configuration.

## Reproducibility

The immutable configuration snapshot is identified by `configuration_id`. Backtest runs reference the configuration snapshot used by the run through `backtest_runs.configuration_id`.

The legacy backtest remains preserved and linked to legacy configuration `1`. V2 research must use new configuration versions for experiments.
