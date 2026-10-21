BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS sex_for_equation VARCHAR(10);

UPDATE users
SET sex_for_equation = CASE LOWER(gender)
    WHEN 'male' THEN 'male'
    WHEN 'female' THEN 'female'
    ELSE sex_for_equation
END
WHERE sex_for_equation IS NULL
  AND gender IS NOT NULL;

ALTER TABLE meal_logs
    ADD COLUMN IF NOT EXISTS calorie_source VARCHAR(30) NOT NULL DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS catalog_calories_per_serving DOUBLE PRECISION;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'users_sex_for_equation_valid'
          AND conrelid = 'users'::regclass
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT users_sex_for_equation_valid
            CHECK (sex_for_equation IS NULL OR sex_for_equation IN ('male', 'female'));
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'meal_logs_calorie_source_valid'
          AND conrelid = 'meal_logs'::regclass
    ) THEN
        ALTER TABLE meal_logs
            ADD CONSTRAINT meal_logs_calorie_source_valid
            CHECK (calorie_source IN ('dish_catalog', 'manual'));
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'meal_logs_catalog_calories_nonnegative'
          AND conrelid = 'meal_logs'::regclass
    ) THEN
        ALTER TABLE meal_logs
            ADD CONSTRAINT meal_logs_catalog_calories_nonnegative
            CHECK (
                catalog_calories_per_serving IS NULL
                OR catalog_calories_per_serving >= 0
            );
    END IF;
END
$$;

COMMIT;
