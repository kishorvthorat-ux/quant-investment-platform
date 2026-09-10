# Dagster Automation

## Pipeline

The quant platform is orchestrated through Dagster.

```text
yahoo_market_data
        |
        v
postgres_market_prices ----+
                            |
nse_trading_calendar       |
        |                   |
        v                   |
postgres_trading_calendar --+
                            |
                            v
                 dbt_v2_performance_build
Assets
yahoo_market_data - downloads market data
postgres_market_prices - loads market prices into PostgreSQL
nse_trading_calendar - ingests the NSE trading calendar
postgres_trading_calendar - loads the official trading calendar
dbt_v2_performance_build - runs the dbt analytics build
Automated Schedule

Schedule: daily_quant_pipeline

Cron: 30 15 * * 1-5 UTC

IST: 21:00, Monday-Friday

The schedule targets dbt_v2_performance_build. Dagster automatically executes its upstream dependencies.

Current Status
Full five-asset pipeline: working
Asset dependency graph: validated
Daily schedule: registered and running
SchedulerDaemon: running through dagster dev
Dagster UI: running locally
Operational Flow
Scheduled trigger
      |
      v
Market data + NSE calendar
      |
      v
PostgreSQL raw data
      |
      v
dbt analytics build
      |
      v
Signals / portfolio outputs
      |
      v
Human review
      |
      v
Broker execution

Broker execution remains manual/human-approved at this stage.

Useful Commands
Validate definitions
.venv/bin/dagster definitions validate -m dagster_quant
List assets
.venv/bin/dagster asset list -m dagster_quant
List schedules
.venv/bin/dagster schedule list -m dagster_quant
Run the complete pipeline manually
.venv/bin/dagster asset materialize -m dagster_quant --select '+dbt_v2_performance_build'
Start Dagster locally
.venv/bin/dagster dev -m dagster_quant
