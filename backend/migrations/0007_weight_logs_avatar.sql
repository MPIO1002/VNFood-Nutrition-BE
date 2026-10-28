-- Migration 0007: adapt existing weight_history table + add avatar_url to users
-- SAFE to run multiple times (all statements are idempotent).
--
-- Context: weight_history already exists in the DB (legacy table with columns:
--   id, user_id, weight, bmi, recorded_at)
-- We only ADD missing columns; we do NOT drop or recreate anything.

-- 1. Add missing columns to weight_history so we can store a note
--    and a precise weight in kg (weight column already exists as weight).
ALTER TABLE weight_history
    ADD COLUMN IF NOT EXISTS note TEXT;

-- 2. Add avatar_url to users profile
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS avatar_url TEXT;

-- 3. Ensure indexes exist for common query patterns
CREATE INDEX IF NOT EXISTS idx_weight_history_user_id
    ON weight_history(user_id);

CREATE INDEX IF NOT EXISTS idx_weight_history_recorded_at
    ON weight_history(user_id, recorded_at DESC);
