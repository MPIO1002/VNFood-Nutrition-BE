BEGIN;

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS gender VARCHAR(50),
    ADD COLUMN IF NOT EXISTS age INTEGER,
    ADD COLUMN IF NOT EXISTS height DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS weight DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS activity_level VARCHAR(50),
    ADD COLUMN IF NOT EXISTS goal VARCHAR(50),
    ADD COLUMN IF NOT EXISTS bmi DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS tdee DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS target_calories DOUBLE PRECISION;

CREATE TABLE IF NOT EXISTS meal_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dish_id INTEGER REFERENCES dishes(id) ON DELETE SET NULL,
    meal_type VARCHAR(50) NOT NULL,
    quantity DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    total_calories DOUBLE PRECISION NOT NULL,
    image_url TEXT,
    consumed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_meal_logs_user_consumed_at
    ON meal_logs(user_id, consumed_at);
CREATE INDEX IF NOT EXISTS idx_meal_logs_dish_id
    ON meal_logs(dish_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'meal_logs_quantity_positive'
          AND conrelid = 'meal_logs'::regclass
    ) THEN
        ALTER TABLE meal_logs
            ADD CONSTRAINT meal_logs_quantity_positive CHECK (quantity > 0);
    END IF;
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'meal_logs_calories_nonnegative'
          AND conrelid = 'meal_logs'::regclass
    ) THEN
        ALTER TABLE meal_logs
            ADD CONSTRAINT meal_logs_calories_nonnegative CHECK (total_calories >= 0);
    END IF;
END
$$;

COMMIT;
