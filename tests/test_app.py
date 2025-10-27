import re
from datetime import datetime
import pytest

from app import create_app
from microjobs.common import wa_link


@pytest.fixture()
def app(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    state = {
        "users": [],
        "jobs": [],
        "next_user_id": 1,
        "next_job_id": 1,
        "accepted_jobs": [],
    }

    import microjobs.api as api_module
    import microjobs.routes as routes_module

    def fake_get_user_by_email(email):
        return next((u for u in state["users"] if u["email"] == email), None)

    def fake_create_user(payload):
        user = dict(payload)
        user.setdefault("status", "active")
        user["id"] = state["next_user_id"]
        state["next_user_id"] += 1
        state["users"].append(user)
        return user

    def fake_list_jobs_api(
        *,
        q=None,
        status=None,
        page=1,
        page_size=20,
        token=None,
        select="*",
        order=None,
        filters=None,
    ):
        jobs = list(state["jobs"])
        if status:
            target = status.split(".", 1)[-1].lower()
            jobs = [j for j in jobs if (j.get("status") or "").lower() == target]
        if filters:
            for key, expr in filters.items():
                if expr.startswith("eq."):
                    value = expr[3:]
                    jobs = [j for j in jobs if str(j.get(key)) == value]
                elif expr.startswith("neq."):
                    value = expr[4:]
                    jobs = [j for j in jobs if str(j.get(key)) != value]
        if q:
            needle = q.lower()
            jobs = [
                j
                for j in jobs
                if needle in (j.get("title", "") + " " + j.get("description", "")).lower()
            ]
        total = len(jobs)
        start = max((page - 1) * page_size, 0)
        end = start + page_size
        return jobs[start:end], total

    def fake_get_job_api(job_id, *, token=None, select="*"):
        for job in state["jobs"]:
            if job["id"] == int(job_id):
                return job
        return None

    def fake_create_job_api(payload):
        job = dict(payload)
        job["id"] = state["next_job_id"]
        state["next_job_id"] += 1
        job.setdefault("status", "open")
        job.setdefault("created_at", datetime.utcnow().isoformat() + "Z")
        if "poster_id" in job and "customer_id" not in job:
            job["customer_id"] = job["poster_id"]
        state["jobs"].append(job)
        return job

    def fake_list_job_categories(*, token=None):
        cats = sorted({j.get("category") for j in state["jobs"] if j.get("category")})
        return cats or [
            "Electrical",
            "Plumbing",
            "Cleaning",
            "Tutoring",
            "IT Help",
        ]

    def fake_list_job_locations(*, token=None):
        locs = sorted({j.get("location") for j in state["jobs"] if j.get("location")})
        return locs or [
            "Georgetown",
            "Linden",
            "Berbice",
        ]

    def fake_get_applications_for_user(job_id, user_id):
        return []

    class DummyResponse:
        def __init__(self, status_code=201, payload=None):
            self.status_code = status_code
            self._payload = payload or []
            self.headers = {}

        def json(self):
            return self._payload

    def fake_requests_post(url, headers=None, json=None, timeout=None):
        state["accepted_jobs"].append({
            "url": url,
            "headers": headers or {},
            "json": json or {},
        })
        payload = [{"id": len(state["accepted_jobs"]), **(json or {})}]
        return DummyResponse(201, payload)

    def fake_pgrst_base_and_headers():
        return "http://postgrest.test", {}

    monkeypatch.setattr(api_module, "get_user_by_email", fake_get_user_by_email)
    monkeypatch.setattr(api_module, "create_user", fake_create_user)
    monkeypatch.setattr(api_module, "list_jobs_api", fake_list_jobs_api)
    monkeypatch.setattr(api_module, "get_job_api", fake_get_job_api)
    monkeypatch.setattr(api_module, "create_job_api", fake_create_job_api)
    monkeypatch.setattr(api_module, "list_job_categories", fake_list_job_categories)
    monkeypatch.setattr(api_module, "list_job_locations", fake_list_job_locations)
    monkeypatch.setattr(api_module, "get_applications_for_user", fake_get_applications_for_user)
    monkeypatch.setattr(routes_module.requests, "post", fake_requests_post)
    monkeypatch.setattr(routes_module, "pgrst_base_and_headers", fake_pgrst_base_and_headers)

    app.test_state = state
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
    assert resp.status_code in (302, 303)
    assert "/jobs" in resp.headers["Location"]


def test_jobs_list_empty_then_seed(client):
    resp = client.get("/jobs")
    assert resp.status_code == 200
    assert b"No jobs" in resp.data or b"No jobs found" in resp.data

    # Seed endpoint now just informs the user; simulate DB seeding for tests
    resp = client.get("/seed", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Seeding is handled by the database" in resp.data

    state = client.application.test_state
    state["jobs"].append({
        "id": state["next_job_id"],
        "title": "Install ceiling fan",
        "description": "Need fan installed, wiring ready.",
        "category": "Electrical",
        "budget_cents": 6000,
        "location": "Georgetown",
        "contact": "5926001234",
        "status": "open",
        "created_at": "2025-08-24T10:00:00+00:00",
    })
    state["next_job_id"] += 1

    resp2 = client.get("/jobs")
    assert resp2.status_code == 200
    assert b"Install ceiling fan" in resp2.data


def test_post_job_requires_customer_login(client):
    resp = client.get("/post-job")
    assert resp.status_code in (302, 303)
    assert "/auth/login" in resp.headers["Location"]

    register_user(client, "Bob Worker", "worker@test.com", "1234", "worker")
    login_user(client, "worker@test.com", "1234")
    resp2 = client.get("/post-job", follow_redirects=True)
    assert resp2.status_code == 200
    assert b"<form" in resp2.data


def test_customer_can_post_job_and_see_detail(client):
    register_user(client, "Alice", "alice@test.com", "1234", "customer")
    login_user(client, "alice@test.com", "1234")

    resp = client.post(
        "/post-job",
        data={
            "title": "Fix sink",
            "description": "Leak under kitchen sink",
            "category": "Plumbing",
            "budget_cents": "5000",
            "location": "Georgetown",
            "contact": "6001234",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    detail_url = resp.headers["Location"]
    assert re.match(r"^.*/job/\d+$", detail_url)

    state = client.application.test_state
    assert len(state["jobs"]) == 1
    job = state["jobs"][0]
    assert job["title"] == "Fix sink"
    assert job.get("poster_id") is not None

    resp2 = client.get(detail_url)
    assert resp2.status_code == 200
    assert b"Fix sink" in resp2.data


def test_worker_can_accept_job_and_redirects_to_whatsapp(client):
    register_user(client, "Alice", "alice@test.com", "1234", "customer")
    login_user(client, "alice@test.com", "1234")
    client.post(
        "/post-job",
        data={
            "title": "Install fan",
            "description": "Wire ready",
            "category": "Electrical",
            "budget_cents": "6000",
            "location": "Georgetown",
            "contact": "6001234",
        },
    )

    client.get("/auth/logout", follow_redirects=True)
    register_user(client, "Bob", "worker@test.com", "1234", "worker")
    login_user(client, "worker@test.com", "1234")
    with client.session_transaction() as sess:
        sess["role"] = "worker"

    job = client.application.test_state["jobs"][0]
    expected_link = wa_link(
        job["contact"],
        "Hi, I saw your task 'Install fan' on JobLink. I'm interested. Is it still available?",
    )

    resp = client.post(f"/jobs/{job['id']}/accept", follow_redirects=False)
    assert resp.status_code in (302, 303)
    assert resp.headers["Location"] == expected_link

    accepted = client.application.test_state["accepted_jobs"]
    assert len(accepted) == 1
    record = accepted[0]
    assert record["url"] == "http://postgrest.test/accepted_jobs"
    assert record["headers"]["Content-Type"] == "application/json"
    assert record["headers"]["Prefer"] == "return=representation"
    assert record["headers"]["Authorization"].startswith("Bearer")
    assert record["json"] == {"job_id": job["id"], "worker_id": 2}


def test_customer_my_jobs_shows_only_their_jobs(client):
    register_user(client, "Alice", "alice@test.com", "1234", "customer")
    login_user(client, "alice@test.com", "1234")
    with client.session_transaction() as sess:
        sess["role"] = "customer"
    client.post(
        "/post-job",
        data={
            "title": "Alice job",
            "description": "A",
            "category": "IT Help",
            "budget_cents": "1000",
            "location": "Georgetown",
            "contact": "6001111",
        },
    )
    client.get("/auth/logout", follow_redirects=True)

    register_user(client, "Bev", "bev@test.com", "1234", "customer")
    login_user(client, "bev@test.com", "1234")
    with client.session_transaction() as sess:
        sess["role"] = "customer"
    client.post(
        "/post-job",
        data={
            "title": "Bev job",
            "description": "B",
            "category": "Cleaning",
            "budget_cents": "2000",
            "location": "Linden",
            "contact": "6002222",
        },
    )

    resp = client.get("/my-jobs")
    assert resp.status_code == 200
    page = resp.get_data(as_text=True)
    assert "Bev job" in page
    assert "Alice job" not in page


def test_search_and_filters(client):
    state = client.application.test_state
    sample_jobs = [
        {
            "id": state["next_job_id"],
            "title": "Install ceiling fan",
            "description": "Need fan installed, wiring ready.",
            "category": "Electrical",
            "budget_cents": 6000,
            "location": "Georgetown",
            "contact": "5926000001",
            "status": "open",
            "created_at": "2025-08-24T10:00:00+00:00",
        },
        {
            "id": state["next_job_id"] + 1,
            "title": "Math tutor for CSEC",
            "description": "Need weekend lessons.",
            "category": "Tutoring",
            "budget_cents": 4000,
            "location": "Berbice",
            "contact": "5926000002",
            "status": "open",
            "created_at": "2025-08-24T11:00:00+00:00",
        },
    ]
    state["jobs"].extend(sample_jobs)
    state["next_job_id"] += len(sample_jobs)

    resp = client.get("/jobs?q=fan")
    assert resp.status_code == 200
    assert b"Install ceiling fan" in resp.data

    resp2 = client.get("/jobs?category=Tutoring")
    assert resp2.status_code == 200
    assert b"Math tutor for CSEC" in resp2.data

    resp3 = client.get("/jobs?location=Georgetown")
    assert resp3.status_code == 200
    assert b"Georgetown" in resp3.data


def test_login_logout_flow(client):
    register_user(client, "User", "user@test.com", "1234", "worker")
    login_user(client, "user@test.com", "1234")

    with client.session_transaction() as sess:
        assert sess.get("user_id") is not None

    r2 = client.get("/auth/logout", follow_redirects=True)
    assert r2.status_code == 200
    assert b"You have been logged out" in r2.data

    with client.session_transaction() as sess:
        assert not sess


def test_admin_page_accessible(client):
    resp = client.get("/admin")
    assert resp.status_code == 404
