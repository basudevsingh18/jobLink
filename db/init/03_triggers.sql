BEGIN;

-------------------------------------------------------------------
-- 1) Generic updated_at touchers
-------------------------------------------------------------------
CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_jobs_touch ON jobs;
CREATE TRIGGER trg_jobs_touch
BEFORE UPDATE ON jobs
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_apps_touch ON job_applications;
CREATE TRIGGER trg_apps_touch
BEFORE UPDATE ON job_applications
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();


-------------------------------------------------------------------
-- 2) Guardrails on applications
--    (a) prevent applying to your own job
--    (b) prevent applying if job is not open
-------------------------------------------------------------------
CREATE OR REPLACE FUNCTION job_applications_prevent_self_apply()
RETURNS trigger AS $$
DECLARE
  _poster BIGINT;
BEGIN
  SELECT poster_id INTO _poster FROM jobs WHERE id = NEW.job_id;
  IF _poster IS NULL THEN
    RAISE EXCEPTION 'Job % does not exist', NEW.job_id USING ERRCODE='P0001';
  END IF;

  IF _poster = NEW.applicant_id THEN
    RAISE EXCEPTION 'You cannot apply to your own job' USING ERRCODE='P0001';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_apps_no_self ON job_applications;
CREATE TRIGGER trg_apps_no_self
BEFORE INSERT ON job_applications
FOR EACH ROW EXECUTE FUNCTION job_applications_prevent_self_apply();


CREATE OR REPLACE FUNCTION job_applications_require_open_job()
RETURNS trigger AS $$
DECLARE
  _status job_status;
BEGIN
  SELECT status INTO _status FROM jobs WHERE id = NEW.job_id;
  IF _status IS NULL THEN
    RAISE EXCEPTION 'Job % not found', NEW.job_id USING ERRCODE='P0001';
  END IF;

  IF _status <> 'open' THEN
    RAISE EXCEPTION 'Cannot apply: job % is not open (current: %)', NEW.job_id, _status USING ERRCODE='P0001';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_apps_require_open_job ON job_applications;
CREATE TRIGGER trg_apps_require_open_job
BEFORE INSERT ON job_applications
FOR EACH ROW EXECUTE FUNCTION job_applications_require_open_job();


-------------------------------------------------------------------
-- 3) Event logging helpers
-------------------------------------------------------------------
CREATE OR REPLACE FUNCTION log_job_event(_job_id BIGINT, _actor_id BIGINT, _type event_type, _note TEXT DEFAULT NULL, _data JSONB DEFAULT '{}'::jsonb)
RETURNS VOID AS $$
BEGIN
  INSERT INTO job_events(job_id, actor_user_id, event_type, data)
  VALUES (_job_id, _actor_id, _type, COALESCE(_data, '{}'::jsonb));
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION log_app_event(_app_id BIGINT, _actor_id BIGINT, _type event_type, _note TEXT DEFAULT NULL, _data JSONB DEFAULT '{}'::jsonb)
RETURNS VOID AS $$
BEGIN
  INSERT INTO application_events(application_id, actor_id, type, note)
  VALUES (_app_id, _actor_id, _type, _note);
END;
$$ LANGUAGE plpgsql;


-------------------------------------------------------------------
-- 4) Auto-log on INSERT
-------------------------------------------------------------------
CREATE OR REPLACE FUNCTION jobs_after_insert_log()
RETURNS trigger AS $$
BEGIN
  -- actor is optional; if you have session mechanism, set it there.
  PERFORM log_job_event(NEW.id, NULL, 'job_created', NULL, NULL);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_jobs_after_insert_log ON jobs;
CREATE TRIGGER trg_jobs_after_insert_log
AFTER INSERT ON jobs
FOR EACH ROW EXECUTE FUNCTION jobs_after_insert_log();


CREATE OR REPLACE FUNCTION apps_after_insert_log()
RETURNS trigger AS $$
BEGIN
  -- record "application_submitted"
  INSERT INTO application_events(application_id, actor_id, type, note)
  VALUES (NEW.id, NEW.applicant_id, 'application_submitted', NULL);

  -- also mirror a lightweight job-level event (optional)
  PERFORM log_job_event(NEW.job_id, NEW.applicant_id, 'application_submitted', NULL,
                        jsonb_build_object('application_id', NEW.id));

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_apps_after_insert_log ON job_applications;
CREATE TRIGGER trg_apps_after_insert_log
AFTER INSERT ON job_applications
FOR EACH ROW EXECUTE FUNCTION apps_after_insert_log();


-------------------------------------------------------------------
-- 5) Auto-log on STATUS CHANGES (UPDATE)
-------------------------------------------------------------------
-- Jobs: detect status transition
CREATE OR REPLACE FUNCTION jobs_after_update_status_log()
RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.status IS DISTINCT FROM OLD.status THEN
    CASE NEW.status
      WHEN 'offered'   THEN PERFORM log_job_event(NEW.id, NULL, 'job_offered',   NULL, NULL);
      WHEN 'accepted'  THEN PERFORM log_job_event(NEW.id, NULL, 'job_accepted',  NULL,
                                 jsonb_build_object('assigned_app_id', NEW.assigned_app_id,
                                                    'assigned_user_id', NEW.assigned_user_id));
      WHEN 'closed'    THEN PERFORM log_job_event(NEW.id, NULL, 'job_closed',    NULL, NULL);
      WHEN 'cancelled' THEN PERFORM log_job_event(NEW.id, NULL, 'job_cancelled', NULL, NULL);
      -- 'draft','open' usually not logged here (creation already logged), but include if useful
      ELSE NULL;
    END CASE;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_jobs_after_update_status_log ON jobs;
CREATE TRIGGER trg_jobs_after_update_status_log
AFTER UPDATE OF status, assigned_app_id, assigned_user_id ON jobs
FOR EACH ROW EXECUTE FUNCTION jobs_after_update_status_log();


-- Applications: detect status transition
CREATE OR REPLACE FUNCTION apps_after_update_status_log()
RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.status IS DISTINCT FROM OLD.status THEN
    CASE NEW.status
      WHEN 'offered'   THEN
        INSERT INTO application_events(application_id, actor_id, type, note)
        VALUES (NEW.id, NULL, 'application_offered', NULL);
        PERFORM log_job_event(NEW.job_id, NULL, 'application_offered', NULL,
                              jsonb_build_object('application_id', NEW.id));

      WHEN 'accepted'  THEN
        INSERT INTO application_events(application_id, actor_id, type, note)
        VALUES (NEW.id, NEW.applicant_id, 'application_accepted', NULL);
        PERFORM log_job_event(NEW.job_id, NEW.applicant_id, 'application_accepted', NULL,
                              jsonb_build_object('application_id', NEW.id));

      WHEN 'declined'  THEN
        INSERT INTO application_events(application_id, actor_id, type, note)
        VALUES (NEW.id, NULL, 'application_declined', NULL);
        PERFORM log_job_event(NEW.job_id, NULL, 'application_declined', NULL,
                              jsonb_build_object('application_id', NEW.id));

      WHEN 'withdrawn' THEN
        INSERT INTO application_events(application_id, actor_id, type, note)
        VALUES (NEW.id, NEW.applicant_id, 'application_withdrawn', NULL);
        PERFORM log_job_event(NEW.job_id, NEW.applicant_id, 'application_withdrawn', NULL,
                              jsonb_build_object('application_id', NEW.id));
      ELSE
        NULL;
    END CASE;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_apps_after_update_status_log ON job_applications;
CREATE TRIGGER trg_apps_after_update_status_log
AFTER UPDATE OF status ON job_applications
FOR EACH ROW EXECUTE FUNCTION apps_after_update_status_log();

COMMIT;
