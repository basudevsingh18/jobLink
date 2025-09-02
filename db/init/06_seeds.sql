-- 06_seeds.sql — minimal seeding: just users and jobs

-- -- USERS
-- INSERT INTO users (name, email, password_hash, status, created_at)
-- VALUES
--   ('Alice Poster',  'alice@example.com',  'hash_alice',  'active', now()),
--   ('Bob Worker',    'bob@example.com',    'hash_bob',    'active', now()),
--   ('Charlie Mixed', 'charlie@example.com','hash_charlie','active', now())
-- ON CONFLICT (email) DO NOTHING;

-- -- JOBS
-- INSERT INTO jobs (poster_id, title, description, category, budget_cents, location, contact, status, created_at)
-- SELECT u.id, 'Fix kitchen sink', 'Need a plumber to fix my leaking sink.', 'Plumbing', 5000, 'Georgetown', 'alice_contact', 'open', now()
-- FROM users u WHERE u.email='alice@example.com'
-- ON CONFLICT DO NOTHING;

-- INSERT INTO jobs (poster_id, title, description, category, budget_cents, location, contact, status, created_at)
-- SELECT u.id, 'Paint my fence', 'Looking for someone to paint fence blue.', 'Painting', 8000, 'Diamond', 'alice_contact', 'open', now()
-- FROM users u WHERE u.email='alice@example.com'
-- ON CONFLICT DO NOTHING;

-- INSERT INTO jobs (poster_id, title, description, category, budget_cents, location, contact, status, created_at)
-- SELECT u.id, 'Assemble bookshelf', 'Need help assembling IKEA bookshelf.', 'Carpentry', 6000, 'East Bank', 'bob_contact', 'open', now()
-- FROM users u WHERE u.email='bob@example.com'

-- 15 Jobs for poster_id 56 or 52

-- 15 Jobs for poster_id 56 or 52, with detailed descriptions

INSERT INTO jobs (poster_id, title, description, category, budget_cents, location, contact, status, created_at)
VALUES
-- poster_id = 56
(56, 'Fix kitchen sink', 
 'Kitchen sink has been leaking for a week. Water drips continuously from the faucet and the under-sink pipe is loose. Need a plumber who can diagnose and repair it quickly. Materials will be provided if needed.', 
 'Plumbing', 5000, 'Georgetown', 'contact_56', 'open', now()),

(56, 'Paint my fence', 
 'Wooden picket fence around my yard needs sanding and repainting. I already bought blue paint and brushes, but I need someone with experience to ensure an even finish that will last through the rainy season.', 
 'Painting', 8000, 'Diamond', 'contact_56', 'open', now()),

(56, 'Assemble bookshelf', 
 'Bought a new IKEA bookshelf that comes with multiple shelves and screws. I need help assembling it properly so that it is sturdy and leveled. Job should take about 1–2 hours.', 
 'Carpentry', 6000, 'East Bank', 'contact_56', 'open', now()),

(56, 'Mow front yard', 
 'Small lawn in front of my house has grown tall and uneven. Need someone with their own mower or weed cutter to trim it neatly. The area is about 20x20 feet.', 
 'Gardening', 3000, 'Georgetown', 'contact_56', 'open', now()),

(56, 'Install ceiling fan', 
 'Looking for an electrician to install a ceiling fan in my living room. Wiring already exists, but I need someone to securely mount the fan and test it for proper operation.', 
 'Electrical', 7000, 'Eccles', 'contact_56', 'open', now()),

(56, 'Repair leaking roof', 
 'Roof started leaking after recent rainfall. Small section above the kitchen has water damage. I need a roofer who can patch the leak and check surrounding shingles for potential issues.', 
 'Roofing', 12000, 'Diamond', 'contact_56', 'open', now()),

(56, 'Clean apartment', 
 'Two-bedroom apartment needs a deep clean, including kitchen, bathroom, windows, and floors. Prefer someone with cleaning supplies who can finish in one day.', 
 'Cleaning', 9000, 'Georgetown', 'contact_56', 'open', now()),


-- poster_id = 52
(52, 'Fix bathroom toilet', 
 'Toilet in master bathroom won’t flush properly. The tank fills up slowly and water keeps running. Need a plumber to inspect and fix or replace the flush mechanism.', 
 'Plumbing', 6000, 'Georgetown', 'contact_52', 'open', now()),

(52, 'Repaint bedroom', 
 'Bedroom walls are old and have peeling paint. Looking for someone to prep the surface, apply primer, and repaint in beige. Room is 12x12 feet, and I will provide the paint.', 
 'Painting', 10000, 'Lusignan', 'contact_52', 'open', now()),

(52, 'Build wooden deck', 
 'Backyard needs a small wooden deck extension, about 10x12 feet. Materials will be supplied, but need someone with carpentry skills to cut, assemble, and secure it properly.', 
 'Carpentry', 25000, 'East Coast', 'contact_52', 'open', now()),

(52, 'Trim hedges', 
 'Front yard hedges have grown uneven. Looking for a gardener to trim them neatly and dispose of the clippings. Hedges are about 5 feet tall and 20 feet long.', 
 'Gardening', 4000, 'Diamond', 'contact_52', 'open', now()),

(52, 'Wire new outlet', 
 'Need an electrician to add an additional power outlet in the living room. Existing wiring is nearby, so the job should be straightforward. Please bring tools and testing equipment.', 
 'Electrical', 8000, 'Providence', 'contact_52', 'open', now()),

(52, 'Install guttering', 
 'Rainwater overflows because of missing gutters at the back of the house. Need someone to install new guttering and downspout to redirect water away from the foundation.', 
 'Roofing', 15000, 'Georgetown', 'contact_52', 'open', now()),

(52, 'Clean office space', 
 'Looking for a reliable cleaner for a small office (3 rooms + restroom). Needs mopping, dusting, and garbage disposal. Work to be done once a week, preferably on weekends.', 
 'Cleaning', 11000, 'East Bank', 'contact_52', 'open', now()),

(52, 'Fix door lock', 
 'Front door lock is jammed and key doesn’t turn smoothly. Need a carpenter or locksmith to either repair or replace the lock mechanism for better security.', 
 'Carpentry', 5000, 'Georgetown', 'contact_52', 'open', now())



ON CONFLICT DO NOTHING;
