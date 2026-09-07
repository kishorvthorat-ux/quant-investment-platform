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
