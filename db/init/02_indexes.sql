-- 02_indexes.sql
BEGIN;

-- USERS
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_last_login_at ON users (last_login_at);

-- JOBS
CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at ON jobs (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_category ON jobs (category);
CREATE INDEX IF NOT EXISTS idx_jobs_location ON jobs (location);
CREATE INDEX IF NOT EXISTS idx_jobs_open_recent ON jobs (created_at DESC) WHERE status IN ('open','offered');
CREATE INDEX IF NOT EXISTS idx_jobs_poster_id_created ON jobs (poster_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_assigned_user_id_created ON jobs (assigned_user_id, created_at DESC);
-- optional FTS column/index if you added it
-- ALTER TABLE jobs ADD COLUMN IF NOT EXISTS search_tsv tsvector GENERATED ALWAYS AS (
--   setweight(to_tsvector('simple', coalesce(title,'')), 'A') ||
--   setweight(to_tsvector('simple', coalesce(description,'')), 'B')
-- ) STORED;
-- CREATE INDEX IF NOT EXISTS idx_jobs_search_tsv ON jobs USING GIN (search_tsv);
-- CREATE INDEX IF NOT EXISTS idx_jobs_title_trgm ON jobs USING GIN (title gin_trgm_ops);

-- APPLICATIONS
CREATE INDEX IF NOT EXISTS idx_apps_job_status_created ON job_applications (job_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_apps_job_outstanding ON job_applications (job_id, created_at DESC) WHERE status IN ('submitted','offered');
CREATE INDEX IF NOT EXISTS idx_apps_applicant_created ON job_applications (applicant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_apps_applicant_status_created ON job_applications (applicant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_apps_job_id ON job_applications (job_id);
CREATE INDEX IF NOT EXISTS idx_apps_applicant_id ON job_applications (applicant_id);
CREATE INDEX IF NOT EXISTS idx_apps_created_at ON job_applications (created_at DESC);

-- EVENTS
CREATE INDEX IF NOT EXISTS idx_job_events_job_id_created ON job_events (job_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_job_events_actor_created ON job_events (actor_user_id, created_at DESC);

COMMIT;
