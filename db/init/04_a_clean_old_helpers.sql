-- 03a_cleanup_old_event_helpers.sql
DO $$
DECLARE
  r record;
BEGIN
  -- drop ANY function named log_app_event(*) in ANY schema
  FOR r IN
    SELECT p.oid::regprocedure AS sig
    FROM pg_proc p
    WHERE p.proname = 'log_app_event'
  LOOP
    EXECUTE format('DROP FUNCTION IF EXISTS %s;', r.sig);
  END LOOP;

  -- drop ANY function named log_job_event(*) in ANY schema
  FOR r IN
    SELECT p.oid::regprocedure AS sig
    FROM pg_proc p
    WHERE p.proname = 'log_job_event'
  LOOP
    EXECUTE format('DROP FUNCTION IF EXISTS %s;', r.sig);
  END LOOP;
END$$;
