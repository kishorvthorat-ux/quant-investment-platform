-- Add immutable configuration lineage to backtest runs.
-- Existing historical runs are backfilled to their exact configuration snapshot.

ALTER TABLE analytics.backtest_runs
ADD COLUMN IF NOT EXISTS configuration_id BIGINT;

UPDATE analytics.backtest_runs br
SET configuration_id = scv.configuration_id
FROM analytics.strategy_config_version scv
WHERE br.run_id = 1
  AND br.strategy_id = scv.strategy_id
  AND scv.configuration_id = 1
  AND br.configuration_id IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_backtest_runs_configuration'
          AND conrelid = 'analytics.backtest_runs'::regclass
    ) THEN
        ALTER TABLE analytics.backtest_runs
        ADD CONSTRAINT fk_backtest_runs_configuration
        FOREIGN KEY (configuration_id)
        REFERENCES analytics.strategy_config_version(configuration_id);
    END IF;
END $$;

ALTER TABLE analytics.backtest_runs
ALTER COLUMN configuration_id SET NOT NULL;
