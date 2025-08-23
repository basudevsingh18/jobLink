import re
import pytest

# We import the Flask app factory and the in-memory stores
from app import create_app
import microjobs.routes as routes
import microjobs.auth as auth


@pytest.fixture(autouse=True)
def reset_state():
    """Reset in-memory stores before each test."""
    # Users
    auth.USERS.clear()
    auth.NEXT_USER_ID = 1
    # Jobs
    routes.JOBS.clear()
    routes.NEXT_ID = 1
    routes.ACCEPTED_JOBS.clear()
    routes.NEXT_ACCEPT_ID = 1
    yield


@pytest.fixture()
def app():
    app = create_app()
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
    )
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


# ---------- Helpers ----------

def register_user(client, name, email, password, role):
    return client.post(
        "/auth/register",
        data={"name": name, "email": email, "password": password, "role": role},
        follow_redirects=True,
    )


def login_user(client, email, password):
    return client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


# ---------- Tests ----------

def test_home_redirects_to_jobs(client):
    resp = client.get("/")
    assert resp.status_code == 302
    assert "/jobs" in resp.headers["Location"]


def test_jobs_list_empty_then_seed(client):
    # Initially empty
    resp = client.get("/jobs")
    assert resp.status_code == 200
    assert b"No jobs" in resp.data or b"No jobs found" in resp.data

    # Seed and verify
    resp = client.get("/seed", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Seeded demo jobs" in resp.data
    # Now jobs should appear
    resp2 = client.get("/jobs")
    assert resp2.status_code == 200
    assert b"Install ceiling fan" in resp2.data


def test_post_job_requires_customer_login(client):
    # Not logged in -> redirected to login
    resp = client.get("/post-job")
    assert resp.status_code in (302, 303)
    assert "/auth/login" in resp.headers["Location"]

    # Logged in as worker -> still blocked
    register_user(client, "Bob Worker", "worker@test.com", "1234", "worker")
    login_user(client, "worker@test.com", "1234")
    resp2 = client.get("/post-job", follow_redirects=True)
    assert b"requires a customer account" in resp2.data


def test_customer_can_post_job_and_see_detail(client):
    # Register + login as customer
    register_user(client, "Alice", "alice@test.com", "1234", "customer")
    login_user(client, "alice@test.com", "1234")

    # Post a job
    resp = client.post(
        "/post-job",
        data={
            "title": "Fix sink",
            "description": "Leak under kitchen sink",
            "category": "Plumbing",
            "budget": "5000",
            "location": "Georgetown",
            "contact": "6001234",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    # Redirect to detail
    detail_url = resp.headers["Location"]
    assert re.match(r"^.*/job/\d+$", detail_url)

    # Verify job stored and linked to customer
    assert len(routes.JOBS) == 1
    job = routes.JOBS[0]
    assert job["title"] == "Fix sink"
    assert job["customer_id"] is not None

    # Visit detail
    resp2 = client.get(detail_url)
    assert resp2.status_code == 200
    assert b"Fix sink" in resp2.data


def test_worker_can_accept_job_and_redirects_to_whatsapp(client):
    # Create a job (as customer)
    register_user(client, "Alice", "alice@test.com", "1234", "customer")
    login_user(client, "alice@test.com", "1234")
    client.post(
        "/post-job",
        data={
            "title": "Install fan",
            "description": "Wire ready",
            "category": "Electrical",
            "budget": "6000",
            "location": "Georgetown",
            "contact": "6001234",
        },
    )

    # Log out customer, log in as worker
    client.get("/auth/logout", follow_redirects=True)
    register_user(client, "Bob", "worker@test.com", "1234", "worker")
    login_user(client, "worker@test.com", "1234")

    # Accept job
    job_id = routes.JOBS[0]["id"]
    resp = client.get(f"/job/{job_id}/accept", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert "https://wa.me/" in resp.headers["Location"]

    # Acceptance logged
    assert len(routes.ACCEPTED_JOBS) == 1
    rec = routes.ACCEPTED_JOBS[0]
    assert rec["job_id"] == job_id


def test_customer_my_jobs_shows_only_their_jobs(client):
    # Customer A posts 1 job
    register_user(client, "Alice", "alice@test.com", "1234", "customer")
    login_user(client, "alice@test.com", "1234")
    client.post(
        "/post-job",
        data={
            "title": "Alice job",
            "description": "A",
            "category": "IT Help",
            "budget": "1000",
            "location": "Georgetown",
            "contact": "6001111",
        },
    )
    client.get("/auth/logout", follow_redirects=True)

    # Customer B posts 1 job
    register_user(client, "Bev", "bev@test.com", "1234", "customer")
    login_user(client, "bev@test.com", "1234")
    client.post(
        "/post-job",
        data={
            "title": "Bev job",
            "description": "B",
            "category": "Cleaning",
            "budget": "2000",
            "location": "Linden",
            "contact": "6002222",
        },
    )

    # /my-jobs should show only Bev's job
    resp = client.get("/my-jobs")
    assert resp.status_code == 200
    page = resp.get_data(as_text=True)
    assert "Bev job" in page
    assert "Alice job" not in page


def test_search_and_filters(client):
    client.get("/seed", follow_redirects=True)
    # Search term
    resp = client.get("/jobs?q=fan")
    assert resp.status_code == 200
    assert b"Install ceiling fan" in resp.data
    # Category filter
    resp2 = client.get("/jobs?category=Tutoring")
    assert resp2.status_code == 200
    assert b"Math tutor for CSEC" in resp2.data
    # Location filter (should include at least one from seed)
    resp3 = client.get("/jobs?location=Georgetown")
    assert resp3.status_code == 200
    assert b"Georgetown" in resp3.data


def test_login_logout_flow(client):
    register_user(client, "User", "user@test.com", "1234", "worker")
    r1 = login_user(client, "user@test.com", "1234")
    assert r1.status_code == 200
    assert b"Welcome back" in r1.data

    r2 = client.get("/auth/logout", follow_redirects=True)
    assert r2.status_code == 200
    assert b"logged out" in r2.data


def test_admin_page_accessible(client):
    # Currently admin is not restricted; page should load even if empty
    resp = client.get("/admin")
    assert resp.status_code == 200

