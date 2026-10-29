-- Migration 0008: Add special condition flags to users table
-- These flags control whether TDEE recalculation is skipped on PATCH /profile.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS pregnant_or_breastfeeding   BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS competitive_athlete          BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS metabolism_affecting_condition BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN users.pregnant_or_breastfeeding
    IS 'True when Mifflin-St Jeor is not appropriate; TDEE recalculation is skipped.';
COMMENT ON COLUMN users.competitive_athlete
    IS 'True when user is a competitive athlete; TDEE recalculation is skipped.';
COMMENT ON COLUMN users.metabolism_affecting_condition
    IS 'True when user has a medical condition or medication affecting metabolism; recalculation skipped.';

