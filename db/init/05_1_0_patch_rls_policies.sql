-- roles (idempotent)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOINHERIT; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOINHERIT; END IF;
END$$;

-- the critical bit: schema visibility
GRANT USAGE ON SCHEMA public TO authenticated, anon;

-- wide open in dev (you already have policies, this reinforces privileges)
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA public TO authenticated, anon;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO authenticated, anon;


-- Create anon role if missing
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
END $$;

-- Allow anon to read from public schema + jobs table (add more as needed)
GRANT USAGE ON SCHEMA public TO anon;
GRANT SELECT ON public.jobs TO anon;

-- If you use RLS on jobs, allow public to read only "open" jobs
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename='jobs' AND policyname='jobs_read_anon'
  ) THEN
    CREATE POLICY jobs_read_anon ON public.jobs
    FOR SELECT TO anon USING (status = 'open');
  END IF;
END $$;
