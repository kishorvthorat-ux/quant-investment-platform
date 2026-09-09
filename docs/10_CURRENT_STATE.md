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
- M_RD_504010_V2: configuration-driven strategy, immutable configuration version 2 currently remains `DRAFT`.
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

## Snapshot Validation Status

The immutable configuration snapshot for `M_RD_504010_V2` (`configuration_id = 2`) is structurally complete and has dedicated dbt validation coverage.

- 4 factor groups are present and enabled.
- 10 configured factors are present and enabled.
- Enabled factor-group weights sum to `1.000000`.
- Enabled feature weights sum to `1.000000`.
- Feature weights reconcile to their configured factor-group weights.
- `strategy_snapshot_group_weights_total` passes.
- `strategy_snapshot_feature_weights_total` passes.
- `strategy_snapshot_feature_weights_match_group` passes.

These tests establish structural validity of the immutable snapshot. They do not promote the configuration through its lifecycle.

Configuration `2` intentionally remains `DRAFT`. No lifecycle promotion mechanism currently exists in the repository, and no automatic DRAFT → VALIDATED → FROZEN transition has been introduced.

## Next Phase

Design the configuration lifecycle and promotion mechanism separately from structural validation, while preserving legacy results and keeping production execution dependent only on validated/frozen configuration snapshots. Do not change live V2 weights or legacy results.

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

## MVP Execution Baseline — 2026-09-08

The configuration-driven MVP execution flow is now validated.

### Active MVP configuration

- Strategy: `M_RD_504010_V2`
- Configuration ID: `2`
- Configuration version: `2`
- Configuration type: `FACTOR_CONFIG`
- Status: `VALIDATED`
- Signal frequency: `WEEKLY`
- Entry rule: `NEXT_TRADING_DAY`
- Rebalance rule: `NEXT_SIGNAL`
- Top N: `2`
- Position weight: `0.50`

### Validated execution behavior

The portfolio selects the top 2 securities at each weekly signal and allocates 50% to each.

The signal is generated on the last available trading day of the calendar week. Positions are entered on the next available trading day and held until the next signal.

Turnover is generated only on entry days where the new signal changes target positions.

Validation results:

- 349 signal dates.
- First signal: 2020-01-03.
- Last signal: 2026-09-03.
- First position: 2020-01-06.
- Last position: 2026-09-04.
- 1,307 position dates.
- 64,039 position rows.
- 286 active-turnover days.
- 286 turnover days occurred on entry days.
- 0 turnover days occurred on non-entry holding days.
- 78.12% of position dates had zero turnover.

### Baseline performance

Current V2 baseline and breadth research state:

| Configuration | Breadth | Net CAGR | Net Sharpe | Net Max DD | Total Turnover |
|---|---:|---:|---:|---:|---:|
| Config 2 | Top-2 | 12.5855% | 0.7514 | -27.7816% | 183.5000 |
| Config 3 | Top-4 | 15.7911% | 1.0099 | -25.7469% | 154.5000 |
| Config 4 | Top-5 | 18.0002% | 1.1628 | -26.8856% | 139.7000 |
| Config 5 | Top-6 | 14.8902% | 1.0215 | -25.4254% | 133.0000 |

Config 2 remains the MVP baseline. Configurations 3-5 are immutable breadth experiments and must not be treated as production promotion decisions.

The authoritative trading calendar is `metadata.trading_calendar`, sourced from the official NSE calendar. `raw.trading_calendar` is maintained as a compatibility mirror for the existing staging model. The current calendar covers 2020-01-01 through 2026-12-31.

The baseline remains weekly signal-based execution: signal on the last available trading day of each calendar week, enter on the next available trading day, and hold until the next signal.

The baseline is a research result and is not yet considered proof of production profitability.

### Warm-up

All 10 configured V2 features become simultaneously available for a security from 2021-01-04. The earlier period is retained as intentional feature warm-up/incomplete history for the MVP.

### Baseline protection

`M_RD_504010_V2` configuration `2` is the frozen-in-design MVP baseline but remains lifecycle `VALIDATED` rather than `FROZEN` until the explicit MVP checkpoint decision is completed.

Factor optimization must use new configuration versions and must not modify configuration `2`.

### MVP scope boundary

The immediate objective is to finalize the baseline flow and establish a reproducible checkpoint.

Deferred until after the MVP checkpoint:

- factor optimization
- CAGR improvement experiments
- lifecycle automation
- approval workflow
- production order execution
- production orchestration
