import re
import pytest

from app import create_app

# -----------------------------
# Fixtures
# -----------------------------
@pytest.fixture()
def app(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    # In-memory “DB” that our monkeypatched API functions will mutate
    state = {
        "jobs": [
            {
                "id": 1,
                "title": "Install ceiling fan",
                "description": "Need fan installed, wiring ready.",
                "category": "Electrical",
                "budget": 6000,
                "location": "Georgetown",
                "contact": "6001234",
                "status": "open",
                "created_at": "2025-08-24T10:00:00+00:00",
            }
        ],
        "next_id": 2,
    }

    # --- monkeypatch PostgREST API calls ---
    import microjobs.api as api

    def fake_list_jobs_api(params=None, token=None):
        jobs = list(state["jobs"])  # copy
        # trivial filter handling for tests
        if params:
            if "category" in params and params["category"].startswith("eq."):
                cat = params["category"][3:]
                jobs = [j for j in jobs if (j.get("category") or "") == cat]
            if "or" in params and "ilike" in params["or"]:
                # crude contains search on title/description for demo
                needle = params["or"].split("*")[1].lower()
                jobs = [j for j in jobs if needle in j["title"].lower() or needle in j["description"].lower()]
        return jobs

    def fake_get_job_api(job_id, token=None):
        for j in state["jobs"]:
            if j["id"] == int(job_id):
                return j
        return None

    def fake_create_job_api(job, token=None):
        new = dict(job)
        new["id"] = state["next_id"]
        state["next_id"] += 1
        # normalize fields like backend would
        new.setdefault("status", "open")
        new.setdefault("created_at", "2025-08-24T12:00:00+00:00")
        state["jobs"].append(new)
        return new

    monkeypatch.setattr(api, "list_jobs_api", fake_list_jobs_api)
    monkeypatch.setattr(api, "get_job_api", fake_get_job_api)
    monkeypatch.setattr(api, "create_job_api", fake_create_job_api)

    # Reset in-memory auth store (your auth.py uses in-memory USERS)
    import microjobs.auth as auth
    auth.USERS.clear()
    auth.NEXT_USER_ID = 1

    return app

@pytest.fixture()
def client(app):
    return app.test_client()

# Helpers to act like a person
def register(client, name, email, password, role):
    return client.post("/auth/register", data={
        "name": name, "email": email, "password": password, "role": role
    }, follow_redirects=True)

def login(client, email, password):
    return client.post("/auth/login", data={"email": email, "password": password}, follow_redirects=True)

# -----------------------------
# Journeys (“simulate a person”)
# -----------------------------

def test_guest_browses_jobs_and_searches(client):
    # Home redirects to /jobs
    r = client.get("/")
    assert r.status_code in (301,302)
    # See job list
    r = client.get("/jobs")
    assert r.status_code == 200
    assert b"Install ceiling fan" in r.data

    # Search
    r = client.get("/jobs?q=fan")
    assert r.status_code == 200
    assert b"Install ceiling fan" in r.data

    # Filter by category
    r = client.get("/jobs?category=Electrical")
    assert r.status_code == 200
    assert b"Install ceiling fan" in r.data

def test_customer_posts_a_job_and_is_redirected_to_detail(client):
    # Register + login as customer
    register(client, "Alice", "alice@test.com", "1234", "customer")
    login(client, "alice@test.com", "1234")

    # Load the form (GET)
    r = client.get("/post-job")
    assert r.status_code == 200

    # Submit the form (POST)
    r = client.post("/post-job", data={
        "title": "Fix sink",
        "description": "Leak under kitchen sink",
        "category": "Plumbing",
        "budget": "5000",
        "location": "Georgetown",
        "contact": "6001234",
    }, follow_redirects=False)

    # Should redirect to /job/<id>
    assert r.status_code in (302, 303)
    detail_url = r.headers["Location"]
    assert re.search(r"/job/\d+$", detail_url)

    # Follow to detail
    r2 = client.get(detail_url)
    assert r2.status_code == 200
    assert b"Fix sink" in r2.data
    # WhatsApp link present (from normalized number)
    assert b"wa.me" in r2.data

def test_worker_opens_job_and_clicks_accept_goes_to_whatsapp(client):
    # Make sure there is a job (seeded in fake API state)
    # Register + login as worker
    register(client, "Bob", "worker@test.com", "1234", "worker")
    login(client, "worker@test.com", "1234")

    # Visit a job
    r = client.get("/job/1")
    assert r.status_code == 200
    assert b"Install ceiling fan" in r.data

    # Click accept → redirect to WhatsApp deep link
    r2 = client.get("/job/1/accept", follow_redirects=False)
    assert r2.status_code in (302, 303)
    assert "https://wa.me/" in r2.headers["Location"]

def test_validation_errors_show_on_post_job(client):
    register(client, "Alice", "alice@test.com", "1234", "customer")
    login(client, "alice@test.com", "1234")

    # Missing required fields
    r = client.post("/post-job", data={
        "title": "", "description": "", "category": "", "budget": "", "location": "", "contact": ""
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"Please fill in all required fields." in r.data

    # Non-integer budget
    r2 = client.post("/post-job", data={
        "title": "Something",
        "description": "desc",
        "category": "IT Help",
        "budget": "5k",                 # invalid
        "location": "Georgetown",
        "contact": "6001234",
    }, follow_redirects=True)
    assert b"Budget must be a whole number" in r2.data
