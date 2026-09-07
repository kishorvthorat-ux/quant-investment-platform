# Quant Investment Platform — Current State

## Snapshot

**Date:** 2026-09-07
**Database:** quant_platform
**PostgreSQL:** Docker container quant-postgres
**dbt:** 1.12.3
**Postgres adapter:** 1.11.0

## Git Baseline

**Branch:** checkpoint/pre-reconciliation-2026-09-07
**HEAD:** 8e214ae checkpoint: pre-reconciliation state 2026-09-07

## Strategy State

- M_RD_504010: frozen legacy strategy, configuration version 1.
- M_RD_504010_V2: active configuration-driven strategy, configuration version 2.
- Legacy strategy remains frozen and must not be modified by V2 development.

## Configuration State

- strategy_config is the strategy-level configuration source.
- strategy_factor_groups stores configurable factor groups and group weights.
- strategy_factors stores configurable feature weights, directions, and group membership.
- strategy_feature_configuration provides the effective derived configuration.
- strategy_config_validation currently reports no configuration violations.

## Scoring State

- quant_features is strategy-agnostic and provides reusable technical features.
- quant_scores remains the legacy hard-coded scoring path.
- strategy_scores_config_driven provides configuration-driven composite scores.
- quant_rankings_v2 currently remains dependent on the legacy quant_scores structure and is not yet fully configuration-driven.

## Portfolio and Backtest State

- V2 portfolio positions, weights, daily returns, turnover, and net-return models exist.
- V2 transaction cost currently contains a hard-coded 0.0020 rate and should consume strategy configuration.
- backtest_runs provides run-level identity and references strategy_config.
- backtest_daily_results and backtest_period_results reference backtest_runs.

## Known Architecture Gaps

1. Configuration version is stored on strategy_config but is not propagated through factor configuration.
2. backtest_runs does not record the exact configuration version used by a run.
3. Several V2 downstream models still assume fixed factor names.
4. Portfolio transaction cost configuration is not fully propagated.
5. Production orchestration and deployment are not yet finalized.

## Next Phase

Establish immutable configuration-version lineage while preserving the frozen legacy strategy and existing backtest results. Then reconcile the downstream V2 pipeline so that ranking, portfolio construction, transaction costs, and backtesting consume the exact selected configuration.

## Configuration Version Lineage — Design Status

As of 2026-09-07, the platform has an explicit documented design for configuration-version lineage.

### Current state

- `strategy_config` contains `configuration_version`, but it is not an immutable identity.
- `strategy_factor_groups` is keyed by `(strategy_id, factor_group_id)`.
- `strategy_factors` is keyed by `(strategy_id, feature_id)`.
- `strategy_feature_configuration` is a derived table.
- `backtest_runs` is identified by `run_id` and currently references only `strategy_id`.
- No existing configuration-version or experiment tables were found in the repository/database inspection.

### Target state

Future backtests must be traceable to an immutable configuration version containing the exact factor-group and feature configuration used for the run.

### Implementation status

**Design documented; database implementation not yet started.**

Existing legacy and V2 configurations remain unchanged.
