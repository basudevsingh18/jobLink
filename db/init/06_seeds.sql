-- 06_seeds.sql — minimal seeding: just users and jobs

-- USERS
INSERT INTO users (name, email, password_hash, status, created_at)
VALUES
  ('Alice Poster',  'alice@example.com',  'hash_alice',  'active', now()),
  ('Bob Worker',    'bob@example.com',    'hash_bob',    'active', now()),
  ('Charlie Mixed', 'charlie@example.com','hash_charlie','active', now())
ON CONFLICT (email) DO NOTHING;

-- JOBS
INSERT INTO jobs (poster_id, title, description, category, budget_cents, location, contact, status, created_at)
SELECT u.id, 'Fix kitchen sink', 'Need a plumber to fix my leaking sink.', 'Plumbing', 5000, 'Georgetown', 'alice_contact', 'open', now()
FROM users u WHERE u.email='alice@example.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (poster_id, title, description, category, budget_cents, location, contact, status, created_at)
SELECT u.id, 'Paint my fence', 'Looking for someone to paint fence blue.', 'Painting', 8000, 'Diamond', 'alice_contact', 'open', now()
FROM users u WHERE u.email='alice@example.com'
ON CONFLICT DO NOTHING;

INSERT INTO jobs (poster_id, title, description, category, budget_cents, location, contact, status, created_at)
SELECT u.id, 'Assemble bookshelf', 'Need help assembling IKEA bookshelf.', 'Carpentry', 6000, 'East Bank', 'bob_contact', 'open', now()
FROM users u WHERE u.email='bob@example.com'
ON CONFLICT DO NOTHING;
