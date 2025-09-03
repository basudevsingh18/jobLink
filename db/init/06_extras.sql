BEGIN;

  -- Materials
  ALTER TABLE jobs
  ADD COLUMN
  IF NOT EXISTS materials_provided boolean DEFAULT NULL;

-- Site visit
ALTER TABLE jobs
  ADD COLUMN
IF NOT EXISTS site_visit_required boolean DEFAULT NULL;

-- Workmen
ALTER TABLE jobs
  ADD COLUMN
IF NOT EXISTS workmen_required boolean DEFAULT NULL;


-- minimal anon role & read access
CREATE ROLE anon
NOLOGIN;
GRANT USAGE ON SCHEMA public TO anon;
GRANT SELECT ON TABLE public.jobs TO anon;

-- If you use RLS, add a read policy (example: only show open jobs)
ALTER TABLE public.jobs ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
  FROM pg_policies
  WHERE schemaname='public' AND tablename='jobs' AND policyname='jobs_read_anon'
  ) THEN
  CREATE POLICY jobs_read_anon ON public.jobs
    FOR
  SELECT TO anon
  USING
  (status = 'open');
END
IF;
END$$;


COMMIT;