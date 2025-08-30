-- 01_tables.sql
BEGIN;

-- enums first (idempotent)
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'job_status') THEN
    CREATE TYPE job_status AS ENUM ('draft','open','offered','accepted','closed','cancelled');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'application_status') THEN
    CREATE TYPE application_status AS ENUM ('submitted','offered','accepted','declined','withdrawn');
  END IF;
END $$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'event_type') THEN
    CREATE TYPE event_type AS ENUM (
      'job_created','job_offered','job_accepted','job_closed','job_cancelled',
      'application_submitted','application_offered','application_accepted','application_declined','application_withdrawn'
    );
  END IF;
END $$;

-- tables (idempotent)
CREATE TABLE IF NOT EXISTS users (
  id               BIGSERIAL PRIMARY KEY,
  name             TEXT NOT NULL,
  email            CITEXT UNIQUE NOT NULL,
  password_hash    TEXT NOT NULL,

  status           TEXT NOT NULL DEFAULT 'pending',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

  email_verified_at   TIMESTAMPTZ,
  phone_verified_at   TIMESTAMPTZ,
  verification_token  TEXT,
  verification_expires TIMESTAMPTZ,

  failed_attempts     INT NOT NULL DEFAULT 0,
  lockout_until       TIMESTAMPTZ,

  terms_version       TEXT,
  terms_accepted_at   TIMESTAMPTZ,

  last_login_at       TIMESTAMPTZ,
  last_login_ip       TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
  id               BIGSERIAL PRIMARY KEY,
  poster_id        BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title            TEXT NOT NULL,
  description      TEXT NOT NULL,
  category         TEXT,
  budget_cents     INT,
  location         TEXT,
  contact          TEXT,

  status           job_status NOT NULL DEFAULT 'open',
  assigned_app_id  BIGINT,
  assigned_user_id BIGINT,

  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS job_applications (
  id               BIGSERIAL PRIMARY KEY,
  job_id           BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  applicant_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  proposal         TEXT,
  bid_cents        INT,
  days_to_complete INT,

  status           application_status NOT NULL DEFAULT 'submitted',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

  UNIQUE(job_id, applicant_id)
);

CREATE TABLE IF NOT EXISTS accepted_jobs (
  job_id         BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  application_id BIGINT NOT NULL REFERENCES job_applications(id) ON DELETE CASCADE,
  worker_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  accepted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (job_id, application_id)
);

CREATE TABLE IF NOT EXISTS job_events (
  id            BIGSERIAL PRIMARY KEY,
  job_id        BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  actor_user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
  event_type    event_type NOT NULL,
  data          JSONB DEFAULT '{}'::jsonb,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Application-level event log (mirrors job_events)
CREATE TABLE IF NOT EXISTS application_events (
  id              BIGSERIAL PRIMARY KEY,
  application_id  BIGINT NOT NULL REFERENCES job_applications(id) ON DELETE CASCADE,
  actor_id        BIGINT REFERENCES users(id) ON DELETE SET NULL,
  type            event_type NOT NULL,
  note            TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;
