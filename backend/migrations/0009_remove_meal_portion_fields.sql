BEGIN;

ALTER TABLE meal_logs
    DROP CONSTRAINT IF EXISTS meal_logs_estimated_portion_nonnegative,
    DROP CONSTRAINT IF EXISTS meal_logs_base_portion_positive;

ALTER TABLE meal_logs
    DROP COLUMN IF EXISTS estimated_portion_g,
    DROP COLUMN IF EXISTS base_portion_g;

COMMIT;