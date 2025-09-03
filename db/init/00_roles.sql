-- db/init/00_roles.sql

-- Create anon and authenticated roles if missing (idempotent)
DO $$BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
END$$;

-- Let roles see the schema
GRANT USAGE ON SCHEMA public TO anon, authenticated;

-- Optional: broad dev-friendly defaults (safe for development; tighten for prod)
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO anon;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO authenticated;
