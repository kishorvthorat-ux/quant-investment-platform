# Quant Investment Platform — Changelog

## 2026-09-07 — Configuration-Driven Strategy Foundation

### Added

- Database-backed strategy configuration.
- Configurable factor groups with group weights.
- Configurable strategy features with feature weights and direction.
- Configuration validation for factor-group and feature relationships.
- Derived strategy feature configuration model.
- Configuration-driven strategy scoring.
- Legacy strategy configuration preserved separately.

### Validated

- Strategy configuration constraints are enforced at the database level.
- Factor groups reference valid strategies.
- Strategy factors reference valid factor groups.
- Strategy factors reference valid catalog features.
- Factor-group weights reconcile to the strategy allocation.
- Feature weights reconcile within the configured factor groups.
- Configuration validation currently returns no violations.

### Current Gap

- Configuration-version lineage is implemented through immutable strategy, factor-group, and factor snapshots.
- `backtest_runs.configuration_id` records the exact configuration snapshot used by each run.
- Some downstream V2 models still contain hard-coded factor assumptions.
- Portfolio transaction cost configuration is not yet fully propagated through the V2 pipeline.
- Downstream backtest result and performance-metric lineage still needs to be reviewed end-to-end.

### Next Controlled Change

Propagate and validate configuration-version lineage through the existing downstream backtest and analytics models without disrupting the frozen legacy strategy or existing backtest results.

## 2026-09-07 — Configuration Version Lineage Design

### Added

- Documented the configuration-version reproducibility gap.
- Defined target immutable configuration-version lineage.
- Defined the relationship between strategy identity, configuration version, factor configuration, and backtest execution.

### Not yet implemented

- No database schema changes have been made.
- Existing V2 configuration remains unchanged.
- Existing legacy and backtest results remain unchanged.

### Next controlled change

Design and implement the smallest version-lineage schema that can capture an immutable configuration snapshot without disrupting the existing strategy and backtest framework.

## 2026-09-07 — Strategy-Level Configuration Version Snapshot

### Added

- Live table `analytics.strategy_config_version` with immutable `configuration_id`.
- Strategy-level snapshot columns aligned to current `strategy_config` attributes.
- Repository create DDL in `sql/09_create_strategy_configuration.sql`.
- Two snapshot rows: frozen legacy version 1 and draft V2 version 2.

### Preserved

- V2 top-level weight columns remain 1.0000 / 0 / 0 / 0.
- Actual V2 factor-group mix remains only in `strategy_factor_groups`.
- Existing backtest run 1 is unchanged and still references `strategy_id` only.

### Not yet implemented

- Versioned factor-group snapshot
- Versioned factor snapshot
- `backtest_runs.configuration_id`

### Next controlled change

Inspect `strategy_factor_groups` and add the smallest versioned factor-group snapshot under `strategy_config_version`. Do not recreate `strategy_config_version`.

## 2026-09-08 — Immutable Configuration Snapshot Validation

### Added

- Dedicated dbt validation tests for immutable configuration snapshots.
- Validation of enabled factor-group weights across each configuration.
- Validation of enabled feature weights across each configuration.
- Validation that enabled feature weights reconcile to their configured factor-group weights.

### Validated

The immutable snapshot for `M_RD_504010_V2` (`configuration_id = 2`) is structurally complete:

- 4 enabled factor groups.
- 10 enabled configured factors.
- Factor-group weights sum to `1.000000`.
- Feature weights sum to `1.000000`.
- Feature weights reconcile to their factor-group weights.

The following dbt tests pass:

- `strategy_snapshot_group_weights_total`
- `strategy_snapshot_feature_weights_total`
- `strategy_snapshot_feature_weights_match_group`

### Lifecycle Boundary

Structural validation does not automatically promote a configuration through its lifecycle.

Configuration `2` intentionally remains `DRAFT`. No lifecycle promotion mechanism currently exists in the repository.

No legacy strategy, existing backtest result, or live V2 configuration values were changed by this validation work.

### Next Controlled Change

Design the configuration lifecycle and promotion mechanism, including ownership of DRAFT → VALIDATED → FROZEN transitions, while keeping structural validation independent from lifecycle promotion.

## 2026-09-08 — MVP Weekly Signal-Based Execution Baseline

- Finalized weekly signal-based execution semantics for `M_RD_504010_V2` configuration `2`.
- Weekly signal uses the last available trading day of each calendar week.
- Entry occurs on the next available trading day.
- Top 2 securities receive 50% target weight each.
- Positions are held until the next weekly signal.
- Turnover occurs only when the new signal changes target positions.
- Validated 349 signal dates, 1,307 position dates, and 64,039 position rows.
- Validated 286 active-turnover days, all occurring on entry days; holding days generated zero turnover.
- Corrected the dbt analytics source definition for `strategy_config`.
- Full dbt test suite remains green: 155 PASS, 0 WARN, 0 ERROR.
- Added strategy and backtesting MVP documentation.
- Established configuration `2` as the protected MVP baseline.
- Factor optimization, lifecycle automation, approval workflow, and production execution remain deferred until after the MVP checkpoint.
