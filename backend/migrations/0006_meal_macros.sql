BEGIN;

ALTER TABLE meal_logs
    ADD COLUMN IF NOT EXISTS protein_g DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS fat_g DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS carb_g DOUBLE PRECISION;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'meal_logs_protein_nonnegative'
          AND conrelid = 'meal_logs'::regclass
    ) THEN
        ALTER TABLE meal_logs
            ADD CONSTRAINT meal_logs_protein_nonnegative CHECK (protein_g IS NULL OR protein_g >= 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'meal_logs_fat_nonnegative'
          AND conrelid = 'meal_logs'::regclass
    ) THEN
        ALTER TABLE meal_logs
            ADD CONSTRAINT meal_logs_fat_nonnegative CHECK (fat_g IS NULL OR fat_g >= 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'meal_logs_carb_nonnegative'
          AND conrelid = 'meal_logs'::regclass
    ) THEN
        ALTER TABLE meal_logs
            ADD CONSTRAINT meal_logs_carb_nonnegative CHECK (carb_g IS NULL OR carb_g >= 0);
    END IF;
END
$$;

COMMIT;
