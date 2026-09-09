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

## DEC-003 — Separate Snapshot Validation from Lifecycle Promotion

**Date:** 2026-09-08
**Status:** Accepted

### Context

Immutable configuration snapshots now provide reproducible configuration identity, including strategy-level, factor-group, and factor-level snapshots. Structural dbt tests can verify that a snapshot is internally complete and that configured weights reconcile correctly.

However, structural validity alone does not establish that a configuration should become eligible for production execution.

### Decision

Treat structural validation and lifecycle promotion as separate concerns.

Structural validation will establish whether an immutable configuration snapshot is internally valid.

Lifecycle promotion will explicitly control transitions such as:

`DRAFT → VALIDATED → FROZEN`

A successful validation must not automatically change the lifecycle status.

Production execution will consume only configurations that have reached the appropriate validated/frozen lifecycle state.

### Current State

Configuration `2` (`M_RD_504010_V2`) is structurally valid but remains `DRAFT`.

The following snapshot validations currently pass:

- `strategy_snapshot_group_weights_total`
- `strategy_snapshot_feature_weights_total`
- `strategy_snapshot_feature_weights_match_group`

No lifecycle promotion mechanism currently exists in the repository.

### Rationale

Separating these concerns:

- prevents accidental promotion of experimental configurations;
- preserves explicit human or workflow-controlled decisions;
- makes the lifecycle auditable;
- allows validation rules to evolve independently from promotion policy;
- keeps production execution protected from mutable or insufficiently reviewed research state.

### Migration Constraint

Do not modify:

- frozen legacy strategy `M_RD_504010`;
- existing legacy backtest results;
- existing V2 configuration weights;
- immutable historical configuration snapshots.

### Next Decision

Determine where lifecycle promotion should be owned and how validation evidence, approval, status transitions, and production eligibility should be recorded.

## DEC-004 — Weekly Signal-Based MVP Execution

**Date:** 2026-09-08
**Status:** Accepted

### Context

The configuration-driven V2 scoring pipeline required an explicit execution model for short-term swing trading. The intended behavior is to generate signals weekly, enter on the next trading day, and hold positions until the next signal.

A fixed holding-period or unconditional weekly rebalance would not represent the intended signal-based strategy.

### Decision

Use weekly signal-based portfolio execution for `M_RD_504010_V2`, configuration `2`.

Execution semantics:

`WEEKLY signal → NEXT_TRADING_DAY entry → TOP-2 → 50%/50% → HOLD → NEXT_SIGNAL`

The weekly signal date is the last available trading day of each calendar week.

Turnover occurs only when the next signal changes target positions.

### Validation

The implementation was behaviorally validated:

- 349 weekly signal dates.
- First signal: 2020-01-03.
- Last signal: 2026-09-03.
- First position: 2020-01-06.
- Last position: 2026-09-04.
- 1,307 position dates.
- 64,039 position rows.
- Each tested signal selected exactly 2 securities.
- Each selected security received 50% target weight.
- 286 active-turnover days were observed.
- All 286 active-turnover days occurred on entry days.
- Zero active-turnover days occurred on non-entry holding days.
- 1,021 of 1,307 position dates had zero turnover (78.12%).

### Rationale

This preserves the intended short-term swing-trading behavior while avoiding unnecessary turnover when the weekly signal remains unchanged.

### Baseline Protection

Configuration `2` is now `VALIDATED` and is treated as the MVP baseline.

Future factor experiments must create new configuration versions and must not mutate the baseline configuration or its immutable snapshot.

### Deferred Work

Factor optimization to improve CAGR and risk-adjusted performance will begin only after the MVP flow is checkpointed.

Lifecycle automation, approval workflows, and production execution controls remain outside the MVP scope.

---

## DEC-005 Official NSE Trading Calendar Integration

**Decision:** Use the official NSE trading calendar as the authoritative source for trading-day determination in the MVP.

**Rationale:**
- Trading days must not be inferred solely from observed market-price data.
- Exchange holidays and special sessions need an explicit calendar source.
- The architecture therefore separates the trading calendar from the price-data source.

**Architecture:**
- `metadata.trading_calendar` — authoritative NSE calendar.
- `raw.trading_calendar` — compatibility mirror for the existing staging layer.
- `stg_trading_calendar` — existing staging interface.
- Yahoo Finance remains the market-price source.

**Current coverage:** 2020-01-01 through 2026-12-31.

**MVP treatment:** Standard NSE sessions are represented using the official trading calendar. Special-session timing beyond the current MVP representation can be refined later without changing the core architecture.

**Impact:** The calendar integration is now part of the reproducible MVP baseline. Existing factor definitions, factor weights, scoring logic, and weekly signal semantics are unchanged.

**Status:** Implemented and validated.
