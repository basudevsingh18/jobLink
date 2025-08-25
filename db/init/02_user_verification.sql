-- ==== Users: verification & accountability (idempotent) ====

-- Add columns only if they don't exist
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='status') THEN
    ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'pending';
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='email_verified_at') THEN
    ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMP NULL;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='phone_verified_at') THEN
    ALTER TABLE users ADD COLUMN phone_verified_at TIMESTAMP NULL;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='verification_token') THEN
    ALTER TABLE users ADD COLUMN verification_token TEXT NULL;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='verification_expires') THEN
    ALTER TABLE users ADD COLUMN verification_expires TIMESTAMP NULL;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='failed_attempts') THEN
    ALTER TABLE users ADD COLUMN failed_attempts INT NOT NULL DEFAULT 0;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='lockout_until') THEN
    ALTER TABLE users ADD COLUMN lockout_until TIMESTAMP NULL;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='terms_version') THEN
    ALTER TABLE users ADD COLUMN terms_version TEXT NULL;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='terms_accepted_at') THEN
    ALTER TABLE users ADD COLUMN terms_accepted_at TIMESTAMP NULL;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='last_login_at') THEN
    ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP NULL;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='last_login_ip') THEN
    ALTER TABLE users ADD COLUMN last_login_ip TEXT NULL;
  END IF;
END $$;

-- Create user_events table if missing
CREATE TABLE IF NOT EXISTS user_events (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  event_detail TEXT NULL,
  ip_address TEXT NULL,
  user_agent TEXT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Create the composite index if missing
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes
    WHERE schemaname = 'public'
      AND indexname  = 'idx_user_events_user_date'
  ) THEN
    CREATE INDEX idx_user_events_user_date ON user_events (user_id, created_at);
  END IF;
END $$;
