-- 05_rls_policies_open.sql  — DEV-OPEN EVERYTHING

-- Ensure roles exist (harmless if they already do)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOINHERIT;
  END IF;
END$$;

-- Helper: enable RLS and create one permissive policy per table
-- The policy is FOR ALL TO public USING (true) WITH CHECK (true) — i.e., fully open.
DO $$
DECLARE
  t text;
  tbls text[] := ARRAY[
    'users',
    'jobs',
    'job_applications',
    'job_events',
    'application_events',
    'accepted_jobs'
  ];
BEGIN
  FOREACH t IN ARRAY tbls LOOP
    -- Skip if table doesn't exist (dev environments may omit some)
    IF EXISTS (
      SELECT 1 FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      WHERE c.relkind = 'r' AND n.nspname = 'public' AND c.relname = t
    ) THEN
      EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
      -- Optional, but keeps behavior consistent even if future restrictive policies are added
      EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', t);

      -- Drop our own open policy if it exists so re-runs are clean
      EXECUTE format('DROP POLICY IF EXISTS open_all ON %I;', t);

      -- Create one wide-open policy for everyone (TO public)
      EXECUTE format(
        'CREATE POLICY open_all ON %I FOR ALL TO public USING (true) WITH CHECK (true);',
        t
      );
    END IF;
  END LOOP;
END$$;

-- Broad GRANTS so PostgREST role checks don't 404 on privileges
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA public TO authenticated, anon;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO authenticated, anon;

-- Also set defaults so newly created objects are open too (run as schema owner)
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL PRIVILEGES ON TABLES    TO authenticated, anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT ALL PRIVILEGES ON SEQUENCES TO authenticated, anon;

-- RPCs (grant if present; ignore if not)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'make_offer') THEN
    GRANT EXECUTE ON FUNCTION make_offer(bigint,bigint,bigint) TO authenticated, anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'accept_offer') THEN
    GRANT EXECUTE ON FUNCTION accept_offer(bigint,bigint,bigint) TO authenticated, anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'withdraw_application') THEN
    GRANT EXECUTE ON FUNCTION withdraw_application(bigint,bigint) TO authenticated, anon;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'cancel_job') THEN
    GRANT EXECUTE ON FUNCTION cancel_job(bigint,bigint) TO authenticated, anon;
  END IF;
END$$;
