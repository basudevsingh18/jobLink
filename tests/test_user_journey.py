import re
import pytest

from app import create_app
from microjobs.common import wa_link


@pytest.fixture()
def app(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True, SECRET_KEY="test-secret")

    state = {
        "jobs": [
            {
                "id": 1,
                "title": "Install ceiling fan",
                "description": "Need fan installed, wiring ready.",
                "category": "Electrical",
                "budget_cents": 6000,
                "location": "Georgetown",
                "contact": "5926001234",
                "status": "open",
                "created_at": "2025-08-24T10:00:00+00:00",
            }
        ],
        "next_job_id": 2,
        "users": [],
        "next_user_id": 1,
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
        job.setdefault("created_at", "2025-08-24T12:00:00+00:00")
        if "poster_id" in job and "customer_id" not in job:
            job["customer_id"] = job["poster_id"]
        state["jobs"].append(job)
        return job

    def fake_list_job_categories(*, token=None):
        cats = sorted({j.get("category") for j in state["jobs"] if j.get("category")})
        return cats or ["Electrical", "Plumbing", "Cleaning"]

    def fake_list_job_locations(*, token=None):
        locs = sorted({j.get("location") for j in state["jobs"] if j.get("location")})
        return locs or ["Georgetown", "Linden", "Berbice"]

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


def register(client, name, email, password, role):
    return client.post(
        "/auth/register",
        data={"name": name, "email": email, "password": password, "role": role},
        follow_redirects=True,
    )


def login(client, email, password):
    return client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=True,
    )


def test_guest_browses_jobs_and_searches(client):
    r = client.get("/")
    assert r.status_code in (301, 302)

    r = client.get("/jobs")
    assert r.status_code == 200
    assert b"Install ceiling fan" in r.data

    r = client.get("/jobs?q=fan")
    assert r.status_code == 200
    assert b"Install ceiling fan" in r.data

    r = client.get("/jobs?category=Electrical")
    assert r.status_code == 200
    assert b"Install ceiling fan" in r.data


def test_customer_posts_a_job_and_is_redirected_to_detail(client):
    register(client, "Alice", "alice@test.com", "1234", "customer")
    login(client, "alice@test.com", "1234")

    r = client.get("/post-job")
    assert r.status_code == 200

    r = client.post(
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

    assert r.status_code in (302, 303)
    detail_url = r.headers["Location"]
    assert re.search(r"/job/\d+$", detail_url)

    r2 = client.get(detail_url)
    assert r2.status_code == 200
    assert b"Fix sink" in r2.data
    assert b"wa.me" in r2.data


def test_worker_opens_job_and_clicks_accept_goes_to_whatsapp(client):
    register(client, "Bob", "worker@test.com", "1234", "worker")
    login(client, "worker@test.com", "1234")
    with client.session_transaction() as sess:
        sess["role"] = "worker"

    r = client.get("/job/1")
    assert r.status_code == 200
    assert b"Install ceiling fan" in r.data

    expected_link = wa_link(
        "5926001234",
        "Hi, I saw your task 'Install ceiling fan' on JobLink. I'm interested. Is it still available?",
    )
    r2 = client.post("/jobs/1/accept", follow_redirects=False)
    assert r2.status_code in (302, 303)
    assert r2.headers["Location"] == expected_link


def test_validation_errors_show_on_post_job(client):
    register(client, "Alice", "alice@test.com", "1234", "customer")
    login(client, "alice@test.com", "1234")

    r = client.post(
        "/post-job",
        data={
            "title": "",
            "description": "",
            "category": "",
            "budget_cents": "",
            "location": "",
            "contact": "",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert b"Please fill in all required fields." in r.data

    r2 = client.post(
        "/post-job",
        data={
            "title": "Something",
            "description": "desc",
            "category": "IT Help",
            "budget_cents": "5k",
            "location": "Georgetown",
            "contact": "6001234",
        },
        follow_redirects=True,
    )
    assert b"budget_cents must be a whole number ($)." in r2.data
