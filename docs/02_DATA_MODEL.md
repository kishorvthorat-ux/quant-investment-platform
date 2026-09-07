# Quant Investment Platform — Data Model

## 1. Purpose

This document defines the authoritative data model for the quant investment platform.

The platform separates:

- Metadata
- Market data
- Reusable features
- Strategy configuration
- Derived strategy scores
- Portfolio construction
- Backtesting
- Performance results

The model must support reproducible research and eventual production execution.

## 2. Strategy Configuration Hierarchy

The current configuration model is:

    strategy_config
        |
        +-- strategy_factor_groups
                    |
                    +-- strategy_factors
                                |
                                +-- metadata.feature_catalog

### strategy_config

Authoritative strategy-level configuration.

Important attributes:

- strategy_id
- strategy_name
- top_n
- position_weight
- transaction_cost_rate
- signal_frequency
- entry_rule
- rebalance_rule
- status
- configuration_version
- configuration_type

Supported configuration types:

- LEGACY
- FACTOR_CONFIG

The table enforces strategy-level weight reconciliation and configuration validity.

## 3. Factor Groups

strategy_factor_groups defines the factor groups used by a strategy.

Each group contains:

- strategy_id
- factor_group_id
- factor_group_name
- group_weight
- enabled
- created_at
- updated_at

The primary key is (strategy_id, factor_group_id).

Factor groups must belong to an existing strategy.

## 4. Strategy Features

strategy_factors defines the features contributing to each factor group.

Each configuration contains:

- strategy_id
- feature_id
- factor_group_id
- feature_weight
- direction
- enabled
- created_at
- updated_at

The model enforces:

    strategy
        -> factor group
            -> feature

Each feature must exist in metadata.feature_catalog.

## 5. Derived Configuration Model

strategy_feature_configuration is a derived configuration representation.

It combines:

    strategy_config
        +
    strategy_factor_groups
        +
    strategy_factors
        +
    metadata.feature_catalog

It is not an independent source of truth.

It exposes:

- strategy metadata
- factor group metadata
- group weights
- feature metadata
- feature parameters
- feature weights
- direction
- enablement state

## 6. Feature Generation

quant_features is strategy-agnostic.

It generates reusable market features such as:

- returns
- moving averages
- price versus moving averages
- volatility
- drawdown
- ATR
- RSI
- supporting price/technical calculations

Feature generation must not contain strategy-specific weights.

## 7. Legacy Scoring

quant_scores represents the existing legacy scoring path.

It contains fixed historical factor calculations and is intentionally preserved for legacy benchmark reproducibility.

It must not be silently changed when the configuration-driven V2 architecture evolves.

## 8. Configuration-Driven Scoring

The configuration-driven path uses:

    strategy_feature_configuration
        |
        v
    strategy_feature_values
        |
        v
    strategy_scores_config_driven

The strategy configuration determines:

- participating features
- factor-group allocation
- feature weights
- direction
- enablement

The scoring implementation should consume configuration rather than hard-coded strategy weights.

## 9. Backtesting

The current backtest model is:

    strategy_config
           |
           v
    backtest_runs
           |
           +-- backtest_daily_results
           |
           +-- backtest_period_results

backtest_runs provides run-level identity:

- run_id
- strategy_id
- run_type
- start_date
- end_date
- executed_at
- status
- performance metrics

Daily and period results reference run_id.

## 10. Configuration Reproducibility Gap

The current schema stores:

    strategy_config.configuration_version

but backtest_runs does not currently store the configuration version used by the run.

Similarly, factor-group and strategy-feature configuration tables are currently keyed by strategy rather than configuration version.

Therefore the current model does not yet provide complete immutable configuration lineage for historical backtests.

Target lineage:

    strategy
        |
        +-- configuration version
        |       |
        |       +-- factor groups
        |       +-- strategy features
        |       +-- strategy rules
        |
        +-- backtest run
                |
                +-- exact configuration version
                        |
                        +-- daily results
                        +-- period results

This gap must be resolved before production-grade reproducibility is considered complete.

## 11. Design Principles

1. Configuration is data, not hard-coded scoring logic.
2. Legacy benchmark logic remains immutable.
3. Reusable features remain strategy-agnostic.
4. Derived configuration models are not sources of truth.
5. Backtest results must remain traceable to their originating configuration.
6. Historical experiments must be reproducible.
7. Referential integrity must be enforced at the database level where appropriate.
8. Research and production execution must remain distinguishable.
