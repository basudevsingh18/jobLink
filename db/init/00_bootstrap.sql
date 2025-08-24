-- Create anon role used by PostgREST
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
END $$;

-- Users table if/when you add auth later (safe to create now)
CREATE TABLE IF NOT EXISTS users (
  id            SERIAL PRIMARY KEY,
  name          TEXT NOT NULL,
  email         TEXT UNIQUE NOT NULL,
  role          TEXT NOT NULL CHECK (role IN ('customer','worker','admin')),
  password_hash TEXT,
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- Jobs table with ALL columns your templates/routes reference
CREATE TABLE IF NOT EXISTS jobs (
  id           SERIAL PRIMARY KEY,
  title        TEXT NOT NULL,
  description  TEXT NOT NULL,
  category     TEXT,                      -- used by filters/UI
  budget       INTEGER,                   -- string in the UI; we cast to int in API calls
  location     TEXT,
  contact      TEXT NOT NULL,             -- for WhatsApp deep link
  status       TEXT NOT NULL DEFAULT 'open',
  created_at   TIMESTAMPTZ DEFAULT now(),
  customer_id  INTEGER REFERENCES users(id) ON DELETE SET NULL
);

-- Accepts (not wired yet; safe to have ready)
CREATE TABLE IF NOT EXISTS accepted_jobs (
  id          SERIAL PRIMARY KEY,
  job_id      INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  worker_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  accepted_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (job_id, worker_id)
);

-- Seed a couple jobs so GET /jobs works instantly
INSERT INTO jobs (title, description, category, budget, location, contact)
VALUES
('Install ceiling fan', 'Need fan installed, wiring ready.', 'Electrical', 6000, 'Georgetown', '6001234'),
('Math tutor for CSEC', 'After-school sessions, 2x per week.', 'Tutoring', 8000, 'Linden', '6448888')
ON CONFLICT DO NOTHING;

-- Permissions so anonymous (no JWT) can read public data
GRANT USAGE ON SCHEMA public TO anon;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO anon;
