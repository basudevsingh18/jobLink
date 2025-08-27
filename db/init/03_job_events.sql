-- jobs (you likely have this already)
-- add these if missing:
--   status text CHECK (status IN ('OPEN','ASSIGNED','COMPLETED','CLOSED')) DEFAULT 'OPEN'
--   assigned_worker_id uuid NULL
--   accepted_at timestamptz NULL

-- transparent event log
CREATE TABLE job_events (
  id            bigserial PRIMARY KEY,
  job_id        bigint NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  actor_user_id uuid   NOT NULL,               -- who did it
  event_type    text   NOT NULL,               -- 'JOB_POSTED','JOB_ACCEPTED','STATUS_CHANGED','COMMENT','CANCELLED'
  data          jsonb  NOT NULL DEFAULT '{}'::jsonb,  -- extra context (old/new status, notes)
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX job_events_job_id_created_idx ON job_events(job_id, created_at DESC);
