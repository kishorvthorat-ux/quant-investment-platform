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
