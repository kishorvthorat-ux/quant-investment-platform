# Quant Investment Platform — Current State

## Snapshot

**Date:** 2026-09-07
**Database:** quant_platform
**PostgreSQL:** Docker container quant-postgres
**dbt:** 1.12.3
**Postgres adapter:** 1.11.0

## Git Baseline

**Branch:** checkpoint/pre-reconciliation-2026-09-07
**HEAD:** d8e1719 docs: define immutable configuration version lineage

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

1. Several V2 downstream models still assume fixed factor names.
2. Portfolio transaction cost configuration is not fully propagated.
3. Backtest result and metric lineage still needs to be reviewed end-to-end beyond `backtest_runs`.
4. Production orchestration and deployment are not yet finalized.

## Next Phase

Propagate configuration-version lineage through the existing backtest and analytics models, while preserving legacy results and keeping production execution dependent only on validated/frozen configuration snapshots. Do not change live V2 weights or legacy results.

## Configuration Version Lineage — Implementation Status

### Implemented

`analytics.strategy_config_version` is live. It is the immutable strategy-level snapshot identity.

- Primary key: `configuration_id`
- Unique: `(strategy_id, configuration_version)`
- FK: `strategy_id` → `analytics.strategy_config`
- Status: `DRAFT | VALIDATED | FROZEN | RETIRED`
- Snapshot columns copy the current `strategy_config` attributes, including the existing four top-level weight columns. Those columns are preserved as stored, not rewritten to match factor-group allocations.

Current rows:

- `configuration_id = 1` / `M_RD_504010` / version 1 / `FROZEN` / `LEGACY`
- `configuration_id = 2` / `M_RD_504010_V2` / version 2 / `DRAFT` / `FACTOR_CONFIG`

Repository DDL: `sql/09_create_strategy_configuration.sql` (create-if-not-exists only; do not rerun as a migration).

### Implemented

`analytics.strategy_config_version_factor_group` provides the immutable factor-group snapshot for each configuration.

- Primary key: `(configuration_id, factor_group_id)`
- FK: `configuration_id` → `analytics.strategy_config_version`
- Group weights and enabled status are snapshotted from the source configuration.

`analytics.strategy_config_version_factor` provides the immutable factor-level snapshot for each configuration.

- Primary key: `(configuration_id, factor_group_id, feature_id)`
- FK: `(configuration_id, factor_group_id)` → `analytics.strategy_config_version_factor_group`
- FK: `feature_id` → `metadata.feature_catalog`
- Feature weights, direction, and enabled status are snapshotted from the source configuration.

Configuration `2` (`M_RD_504010_V2`) contains 4 factor groups and 10 factors. Group weights sum to `1.000000`, factor weights sum to `1.000000`, and all group/factor weights reconcile exactly.

`analytics.backtest_runs.configuration_id` is live and `NOT NULL`.

- FK: `configuration_id` → `analytics.strategy_config_version`
- Existing `run_id = 1` is linked to `configuration_id = 1` (`M_RD_504010`, version 1, `FROZEN`, `LEGACY`).
- Historical backtest results and metrics were not changed.

Repository DDL:
- `sql/09_create_strategy_configuration.sql` — strategy, factor-group, and factor version snapshots.
- `sql/10_add_backtest_configuration_lineage.sql` — backtest configuration lineage migration.

Mutable sources remain:

- `strategy_factor_groups` keyed by `(strategy_id, factor_group_id)`
- `strategy_factors` keyed by `(strategy_id, feature_id)`

Existing legacy and V2 configurations remain unchanged.
