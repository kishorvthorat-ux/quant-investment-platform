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

- configuration_version exists on strategy_config but is not yet propagated to factor configuration rows.
- backtest_runs does not yet record the configuration version used by a run.
- Some downstream V2 models still contain hard-coded factor assumptions.
- Portfolio transaction cost configuration is not yet fully propagated through the V2 pipeline.

### Next Controlled Change

Design and implement configuration-version lineage without disrupting the frozen legacy strategy or existing backtest results.

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
