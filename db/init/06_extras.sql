BEGIN;

-- Materials
ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS materials_provided boolean DEFAULT NULL;

-- Site visit
ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS site_visit_required boolean DEFAULT NULL;

-- Workmen
ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS workmen_required boolean DEFAULT NULL;

COMMIT;