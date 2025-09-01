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
