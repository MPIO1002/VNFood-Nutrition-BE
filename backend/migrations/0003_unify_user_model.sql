BEGIN;

-- Refresh tokens are short-lived session data. Recreate the table so its
-- foreign key targets the canonical nutrition user record.
DROP TABLE IF EXISTS auth_refresh_tokens;
DROP TABLE IF EXISTS app_users;

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name VARCHAR(120),
    gender VARCHAR(50),
    age INTEGER,
    height DOUBLE PRECISION,
    weight DOUBLE PRECISION,
    activity_level VARCHAR(50),
    goal VARCHAR(50),
    bmi DOUBLE PRECISION,
    tdee DOUBLE PRECISION,
    target_calories DOUBLE PRECISION,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE TABLE auth_refresh_tokens (
    id UUID PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash CHAR(64) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    replaced_by_token_id UUID REFERENCES auth_refresh_tokens(id) ON DELETE SET NULL
);

CREATE INDEX idx_auth_refresh_tokens_user_id
    ON auth_refresh_tokens(user_id);
CREATE INDEX idx_auth_refresh_tokens_expires_at
    ON auth_refresh_tokens(expires_at);

COMMIT;
