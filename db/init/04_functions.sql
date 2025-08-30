-- 04_functions.sql — minimal, unambiguous

-- 0) Clean out any old conflicting helper overloads
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig
    FROM pg_proc p
    WHERE p.proname IN ('log_job_event','log_app_event')
  LOOP
    EXECUTE format('DROP FUNCTION IF EXISTS %s;', r.sig);
  END LOOP;
END$$;

-- 1) Minimal helpers (single, canonical signatures)

-- matches legacy triggers: (job_id, actor_id, event_type, note, data)
CREATE OR REPLACE FUNCTION public.log_job_event(
  _job_id BIGINT, _actor_id BIGINT, _type event_type, _note TEXT, _data JSONB DEFAULT '{}'::jsonb
) RETURNS VOID AS $$
BEGIN
  INSERT INTO job_events(job_id, actor_user_id, event_type, data, created_at)
  VALUES (_job_id, _actor_id, _type, COALESCE(_data, '{}'::jsonb), now());
END;
$$ LANGUAGE plpgsql;

-- application events (same 5-arg shape for consistency)
CREATE OR REPLACE FUNCTION public.log_app_event(
  _app_id BIGINT, _actor_id BIGINT, _type event_type, _note TEXT, _data JSONB DEFAULT NULL
) RETURNS VOID AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_class WHERE relname='application_events') THEN
    INSERT INTO application_events(application_id, actor_id, type, note, created_at)
    VALUES (_app_id, _actor_id, _type, _note, now());
  END IF;
END;
$$ LANGUAGE plpgsql;

-- 2) Minimal RPCs (write directly; no helper calls to avoid overload issues)

-- Poster → make an offer (job must be open; app must be submitted)
CREATE OR REPLACE FUNCTION public.make_offer(_job_id BIGINT, _app_id BIGINT, _actor_id BIGINT)
RETURNS VOID AS $$
DECLARE
  _poster BIGINT;
  _job_status job_status;
  _applicant BIGINT;
  _app_status application_status;
BEGIN
  SELECT poster_id, status INTO _poster, _job_status
  FROM jobs WHERE id = _job_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Job % not found', _job_id USING ERRCODE='P0001'; END IF;
  IF _poster <> _actor_id THEN RAISE EXCEPTION 'Only the job poster can make an offer' USING ERRCODE='P0001'; END IF;
  IF _job_status <> 'open' THEN RAISE EXCEPTION 'Job % must be open to make an offer (current: %)', _job_id, _job_status USING ERRCODE='P0001'; END IF;

  SELECT applicant_id, status INTO _applicant, _app_status
  FROM job_applications WHERE id=_app_id AND job_id=_job_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Application % not found for job %', _app_id, _job_id USING ERRCODE='P0001'; END IF;
  IF _app_status <> 'submitted' THEN
    RAISE EXCEPTION 'Application % must be submitted to offer (current: %)', _app_id, _app_status USING ERRCODE='P0001';
  END IF;

  UPDATE job_applications SET status='offered', updated_at=now() WHERE id=_app_id;
  UPDATE jobs SET status='offered', updated_at=now() WHERE id=_job_id;

  -- direct event writes (avoid helper ambiguity)
  INSERT INTO job_events(job_id, actor_user_id, event_type, data, created_at)
  VALUES (_job_id, _actor_id, 'job_offered', '{}'::jsonb, now());

  IF EXISTS (SELECT 1 FROM pg_class WHERE relname='application_events') THEN
    INSERT INTO application_events(application_id, actor_id, type, note, created_at)
    VALUES (_app_id, _actor_id, 'application_offered', NULL, now());
  END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Applicant → accept an offer
CREATE OR REPLACE FUNCTION public.accept_offer(_job_id BIGINT, _app_id BIGINT, _actor_id BIGINT)
RETURNS VOID AS $$
DECLARE
  _job_status job_status;
  _app_status application_status;
  _applicant  BIGINT;
BEGIN
  SELECT status INTO _job_status FROM jobs WHERE id=_job_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Job % not found', _job_id USING ERRCODE='P0001'; END IF;

  SELECT status, applicant_id INTO _app_status, _applicant
  FROM job_applications WHERE id=_app_id AND job_id=_job_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Application % not found for job %', _app_id, _job_id USING ERRCODE='P0001'; END IF;

  IF _actor_id <> _applicant THEN RAISE EXCEPTION 'Only the offered applicant can accept' USING ERRCODE='P0001'; END IF;
  IF _job_status <> 'offered' THEN RAISE EXCEPTION 'Job % is not offered (current: %)', _job_id, _job_status USING ERRCODE='P0001'; END IF;
  IF _app_status <> 'offered' THEN RAISE EXCEPTION 'Application % is not offered (current: %)', _app_id, _app_status USING ERRCODE='P0001'; END IF;

  UPDATE jobs
     SET status='accepted',
         assigned_app_id=_app_id,
         assigned_user_id=_actor_id,
         updated_at=now()
   WHERE id=_job_id;

  UPDATE job_applications SET status='accepted', updated_at=now() WHERE id=_app_id;

  UPDATE job_applications
     SET status='declined', updated_at=now()
   WHERE job_id=_job_id AND id<>_app_id AND status IN ('submitted','offered');

  INSERT INTO accepted_jobs(job_id, application_id, worker_id, accepted_at)
  VALUES (_job_id, _app_id, _actor_id)
  ON CONFLICT DO NOTHING;

  -- direct event writes
  INSERT INTO job_events(job_id, actor_user_id, event_type, data, created_at)
  VALUES (_job_id, _actor_id, 'job_accepted', '{}'::jsonb, now());

  IF EXISTS (SELECT 1 FROM pg_class WHERE relname='application_events') THEN
    INSERT INTO application_events(application_id, actor_id, type, note, created_at)
    VALUES (_app_id, _actor_id, 'application_accepted', NULL, now());
  END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 3) Grants for PostgREST roles
GRANT EXECUTE ON FUNCTION public.make_offer(bigint,bigint,bigint)   TO authenticated, anon;
GRANT EXECUTE ON FUNCTION public.accept_offer(bigint,bigint,bigint) TO authenticated, anon;
