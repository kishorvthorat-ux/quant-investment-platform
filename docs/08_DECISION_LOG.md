# Quant Investment Platform — Decision Log

## DEC-001 — Configuration-Driven Factor Architecture

**Date:** 2026-09-07
**Status:** Accepted

### Context

The platform must support multiple strategy configurations without changing scoring code. Factor groups, feature weights, feature direction, and enablement must be configurable and reproducible.

### Decision

Use database-backed strategy configuration as the source of truth. The configuration hierarchy is strategy_config → strategy_factor_groups → strategy_factors → metadata.feature_catalog.

Legacy scoring remains preserved separately. Configuration-driven scoring consumes the effective configuration rather than hard-coded strategy weights.

### Rationale

- Supports experimentation without modifying scoring logic.
- Allows different factor-group allocations and feature weights.
- Provides explicit configuration metadata and validation.
- Separates reusable feature generation from strategy-specific decisions.

### Impact

The configuration model becomes the control plane for strategy research. Derived configuration and scoring models must consume this configuration rather than duplicate strategy logic.

### Rejected Alternative

Hard-coded composite scoring formulas for each strategy.

### Related Reproducibility Gap

strategy_config already contains configuration_version, but factor configuration and backtest_runs do not yet carry configuration-version lineage. This must be addressed before production-grade historical reproducibility is considered complete.

## DEC-002 — Immutable Configuration Version Lineage

**Date:** 2026-09-07
**Status:** Accepted

### Context

The platform supports configuration-driven strategies, but the current configuration tables are mutable and do not provide an immutable identity for a complete strategy configuration.

`strategy_config.configuration_version` exists, but `strategy_config` is keyed only by `strategy_id`. Factor groups and factors are also keyed by strategy rather than configuration version. Therefore, the current version number alone does not guarantee historical reproducibility.

### Decision

Introduce an explicit immutable configuration-version lineage model.

A configuration version will represent the exact strategy configuration used for validation, experimentation, and backtesting.

Backtest runs will ultimately reference the configuration version used for execution.

### Rationale

This enables:

- reproducible historical experiments
- comparison of multiple configurations
- immutable backtest lineage
- auditability of production decisions
- Configure → Validate → Backtest → Compare → Keep/Reject workflow

### Migration constraint

Do not disrupt:

- frozen legacy strategy `M_RD_504010`
- active configuration-driven strategy `M_RD_504010_V2`
- existing backtest results
- existing working scoring and portfolio pipelines

The implementation will proceed incrementally after the target schema is reviewed.

### Implementation progress

Strategy-level snapshot table `analytics.strategy_config_version` is in place. Factor-group and factor snapshots are not yet versioned. `backtest_runs` still references `strategy_id` only.
