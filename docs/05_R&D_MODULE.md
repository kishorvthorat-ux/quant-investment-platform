# R&D / Strategy Research Module

## 1. Purpose

The R&D module is the controlled research environment for testing factor, weight, portfolio, and robustness hypotheses before promoting a configuration to the production signal-generation layer.

R&D experiments must not modify existing validated or frozen configurations.

## 2. Architecture

Production and research are separate paths.

PRODUCTION:
PostgreSQL Market Data -> quant_rankings_v2 -> portfolio_weights_v2 -> weekly_signals_v2 -> Signal Review

RESEARCH:
Historical Market Data -> DuckDB Research Layer -> Factor Calculation -> Factor Ablation / Weight Experiments / Top-N Experiments / Transaction Cost Sensitivity / Robustness Testing -> Experiment Results -> R&D Review -> Reject or Validate -> New strategy_config_version -> Production Signal Path

## 3. Core Principles

1. Existing production V2 strategy logic remains unchanged.
2. Existing validated/frozen configurations are immutable.
3. R&D experiments operate independently of production configuration records.
4. Every experiment must identify its base configuration.
5. Every experiment must record the parameters changed.
6. Results must be reproducible.
7. Validation is an explicit human decision.
8. Only validated experiments can create a new configuration version.
9. R&D must not directly create broker orders or actual executions.
10. Actual execution tracking and P&L remain a separate future module.

## 4. Research Data Layer

DuckDB is the research and experimentation layer.

Database:
duckdb/analytics.duckdb

Current research table:
analytics.market_prices

Columns:
- trade_date
- symbol
- exchange
- open
- high
- low
- close
- volume

The DuckDB research dataset must eventually contain sufficient historical OHLCV data for reproducible factor calculations and backtesting.

## 5. Factor Model

The current configuration-driven factor model contains four factor groups.

### Momentum

Group weight: 40%

- RETURN_20D: 15%
- RETURN_60D: 15%
- RETURN_252D: 10%

### Risk

Group weight: 20%

- VOLATILITY_20D: 7%
- VOLATILITY_60D: 7%
- VOLATILITY_252D: 6%

Risk factors use NEGATIVE direction.

### Drawdown

Group weight: 15%

- DRAWDOWN_252D: 15%

### Trend

Group weight: 25%

- PRICE_VS_MA_20D: 8%
- PRICE_VS_MA_60D: 8%
- PRICE_VS_MA_252D: 9%

Factor weights reconcile to 100%.

## 6. R&D Experiment Types

### 6.1 Factor Ablation

Determine the contribution of factor groups and individual factors.

Initial experiments:
- Full model baseline
- Momentum removed
- Trend removed
- Risk removed
- Drawdown removed
- Individual factor removal
- Selected factor combinations

Every experiment is compared against the same baseline.

### 6.2 Weight Experiments

Test alternative factor-group and individual-factor weights while maintaining valid weight reconciliation.

Example baseline:
- Momentum 40%
- Trend 25%
- Risk 20%
- Drawdown 15%

### 6.3 Top-N Experiments

Evaluate different portfolio breadth:
- Top 2
- Top 3
- Top 4
- Top 5
- Top 6
- Other values where appropriate

Position weights must reconcile with the selected Top-N methodology.

### 6.4 Transaction Cost Sensitivity

Evaluate performance under different transaction-cost assumptions and determine whether apparent performance survives realistic implementation costs.

### 6.5 Robustness Testing

Eventually include:
- Year-by-year performance
- Market-regime analysis where practical
- Train / validation / test periods
- Walk-forward analysis
- Drawdown
- Volatility
- Sharpe
- Win rate
- Turnover
- Transaction costs
- Factor contribution stability
- Performance stability across periods

A configuration must not be selected solely because it has the highest full-period return.

## 7. Experiment Lifecycle

DRAFT -> RUNNING -> COMPLETED -> REVIEWED -> VALIDATED or REJECTED

An experiment may be rerun using the same parameters for reproducibility.

## 8. Experiment Registry

Each experiment should record at minimum:
- experiment_id
- base_configuration_id
- experiment_type
- experiment_name
- parameters_changed
- created_at
- status
- result_summary
- decision

The registry must allow historical research decisions to be reproduced.

## 9. Evaluation Framework

Experiments are compared against their base configuration.

Primary metrics:
- Net return
- Net CAGR
- Net Sharpe
- Maximum drawdown
- Win rate
- Turnover
- Transaction cost

Secondary diagnostics:
- Gross return
- Gross CAGR
- Volatility
- Best day
- Worst day
- Yearly results
- Factor contribution
- Stability across periods

## 10. Validation

Validation is a controlled promotion process.

R&D Experiment -> Evaluation -> Human Review -> Reject OR Validate

If validated, the experiment creates a new immutable configuration version.

Existing configurations must never be overwritten.

## 11. Streamlit R&D Lab

The Streamlit application will contain:

🔬 Strategy R&D Lab

The user should be able to:
1. Select a base configuration.
2. Select experiment type.
3. Adjust permitted parameters.
4. Create an experiment.
5. Run the experiment.
6. View results.
7. Compare against the base configuration.
8. Review robustness diagnostics.
9. Reject or validate the experiment.

The UI must not implement a second version of production strategy logic.

## 12. Production Promotion

Validated experiment -> strategy_config_version -> quant_rankings_v2 -> portfolio_weights_v2 -> weekly_signals_v2 -> Signal Review

Existing signal generation and exit logic must not be changed as part of this promotion workflow.

## 13. Future Execution Module

Actual trading execution is intentionally outside this module.

Future architecture:
Signal Review -> Execution Module -> Broker Orders / Execution Ledger / Actual Positions / Realized P&L / Unrealized P&L

The R&D module must not be coupled to broker execution.

## 14. Implementation Sequence

### R&D-01
Repair and populate DuckDB with the required historical market data.

### R&D-02
Build and verify the factor calculation layer.

### R&D-03
Reconcile calculated factors against existing configuration-driven production factor results.

### R&D-04
Build factor-group ablation.

### R&D-05
Build individual-factor ablation.

### R&D-06
Build weight experiments.

### R&D-07
Build Top-N and transaction-cost experiments.

### R&D-08
Build robustness and walk-forward analysis.

### R&D-09
Build experiment registry.

### R&D-10
Build Streamlit R&D Lab.

### R&D-11
Build explicit validation and configuration-version promotion.

## 15. Guardrails

The following must never happen accidentally:
- R&D experiment overwrites a validated configuration.
- R&D experiment changes frozen strategy logic.
- R&D UI creates real broker orders.
- R&D calculations silently replace production calculations.
- A configuration is promoted without explicit validation.
- Signal or exit logic is changed as a side effect of an R&D experiment.

The research layer must remain isolated, reproducible, auditable, and separate from production signal generation.
