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

The core configuration-version lineage is now implemented through immutable configuration snapshots, versioned factor configuration, and `backtest_runs.configuration_id`. Downstream backtest results and performance metrics still require end-to-end lineage review before production-grade historical reproducibility is considered complete.

## DEC-002 — Immutable Configuration Version Lineage

**Date:** 2026-09-07
**Status:** Accepted

### Context

The platform supports configuration-driven strategies, while the working configuration tables remain mutable control-plane tables.

`strategy_config.configuration_version` alone does not provide immutable historical identity because `strategy_config` is keyed by `strategy_id`. An immutable configuration-version layer is therefore required to snapshot the complete configuration used for validation, experimentation, and backtesting.

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

The immutable configuration-version lineage is now implemented.

- `analytics.strategy_config_version` stores the immutable strategy-level configuration snapshot and `configuration_id`.
- `analytics.strategy_config_version_factor_group` stores immutable factor-group snapshots keyed by `(configuration_id, factor_group_id)`.
- `analytics.strategy_config_version_factor` stores immutable factor snapshots keyed by `(configuration_id, factor_group_id, feature_id)`.
- `analytics.backtest_runs.configuration_id` records the exact configuration snapshot used by each backtest run.
- Existing legacy backtest results were preserved unchanged and linked to their corresponding legacy configuration snapshot.

Remaining work is to review and propagate lineage through downstream backtest results and performance metrics.
