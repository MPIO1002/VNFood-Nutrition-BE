BEGIN;

ALTER TABLE meal_logs
    ADD COLUMN IF NOT EXISTS estimated_portion_g DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS base_portion_g DOUBLE PRECISION;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'meal_logs_estimated_portion_nonnegative'
          AND conrelid = 'meal_logs'::regclass
    ) THEN
        ALTER TABLE meal_logs
            ADD CONSTRAINT meal_logs_estimated_portion_nonnegative
            CHECK (estimated_portion_g IS NULL OR estimated_portion_g >= 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'meal_logs_base_portion_positive'
          AND conrelid = 'meal_logs'::regclass
    ) THEN
        ALTER TABLE meal_logs
            ADD CONSTRAINT meal_logs_base_portion_positive
            CHECK (base_portion_g IS NULL OR base_portion_g > 0);
    END IF;
END $$;

COMMIT;
