-- Migration 0007: add weight_logs table for tracking weight history
-- Apply this file once against your Neon database before starting the server.

-- Weight log table to track weight updates over time
CREATE TABLE IF NOT EXISTS weight_logs (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    weight_kg   DOUBLE PRECISION NOT NULL CHECK (weight_kg > 0 AND weight_kg <= 700),
    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note        TEXT
);

CREATE INDEX IF NOT EXISTS idx_weight_logs_user_id
    ON weight_logs(user_id);

CREATE INDEX IF NOT EXISTS idx_weight_logs_recorded_at
    ON weight_logs(user_id, recorded_at DESC);

-- Add avatar_url column to users if not present
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS avatar_url TEXT;
