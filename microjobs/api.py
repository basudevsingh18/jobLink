# microjobs/api.py
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import smtplib
from flask import current_app
import requests
from typing import Any, Dict, Optional
from werkzeug.security import generate_password_hash

from microjobs.common import pgrst_base_and_headers

# -----------------------------
# PostgREST base + headers
# -----------------------------
BASE = os.getenv("POSTGREST_BASE", "http://localhost:3000").rstrip("/")
HEADERS = {
    "Content-Type": "application/json",
    "Prefer": "return=representation",  # return rows after insert/update/delete
}

PASSWORD_METHOD = os.getenv("PASSWORD_METHOD", "pbkdf2:sha256")

def _headers(token: Optional[str] = None, extra: Optional[dict] = None):
    h = {"Accept": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if extra:
        h.update(extra)
    return h

# ---- Facet helpers: distinct categories/locations ----
def _distinct_values(table: str, column: str, *, token: str | None = None, limit: int = 2000) -> list[str]:
    """
    Return a sorted, de-duplicated list of non-null values for a single column.
    Uses a simple select + client-side dedupe (PostgREST has no 'distinct' param).
    """
    params = {
        "select": column,
        column: "not.is.null",          # filter out NULLs
        "order": f"{column}.asc",       # stable order from API
        "limit": str(limit),
    }
    r = requests.get(f"{BASE}/{table}", params=params, headers=_headers(token), timeout=10)
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.reason} :: {r.text}")
    seen, out = set(), []
    for row in r.json():
        v = row.get(column)
        if v is not None and v not in seen:
            seen.add(v)
            out.append(v)
    return out

def list_job_categories(*, token: str | None = None) -> list[str]:
    return _distinct_values("jobs", "category", token=token)

def list_job_locations(*, token: str | None = None) -> list[str]:
    return _distinct_values("jobs", "location", token=token)


def get_applications_for_user(job_id, user_id):
    base, headers = pgrst_base_and_headers()
    r = requests.get(
        f"{base}/job_applications",
        headers=headers,
        params={"job_id": f"eq.{job_id}", "applicant_id": f"eq.{user_id}"},
        timeout=6,
    )
    r.raise_for_status()
    return r.json()


# -----------------------------
# Users
# -----------------------------
def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    r = requests.get(
        f"{BASE}/users",
        params={"email": f"eq.{email}", "limit": "1"},
        timeout=10,
    )
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.reason} :: {r.text}")
    rows = r.json()
    return rows[0] if rows else None

def create_user(payload: dict) -> Dict[str, Any]:
    resp = requests.post(f"{BASE}/users", json=payload, headers=HEADERS, timeout=10)
    if not resp.ok:
        raise RuntimeError(f"{resp.status_code} {resp.reason} :: {resp.text}")
    data = resp.json()
    return data[0] if isinstance(data, list) and data else data

def update_user(user_id: int | str, payload: dict, *, token: str | None = None) -> Dict[str, Any]:
    """Patch a user by primary key id."""
    r = requests.patch(
        f"{BASE}/users",
        params={"id": f"eq.{user_id}"},
        json=payload,
        headers=_headers(token, extra=HEADERS),
        timeout=10,
    )
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.reason} :: {r.text}")
    data = r.json()
    return data[0] if isinstance(data, list) and data else data

def update_user_by_email(email: str, payload: dict, *, token: str | None = None) -> Dict[str, Any]:
    """Patch a user by email (requires unique email)."""
    r = requests.patch(
        f"{BASE}/users",
        params={"email": f"eq.{email}"},
        json=payload,
        headers=_headers(token, extra=HEADERS),
        timeout=10,
    )
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.reason} :: {r.text}")
    data = r.json()
    return data[0] if isinstance(data, list) and data else data

def update_user_password(email: str, new_password: str, *, token: str | None = None):
    pw_hash = generate_password_hash(new_password, method=PASSWORD_METHOD)
    return update_user_by_email(email, {"password_hash": pw_hash}, token=token)

# -----------------------------
# User events (audit)
# -----------------------------
def create_user_event(data: dict):
    """
    Insert an event into user_events via PostgREST.
    Expected keys:
      - user_id (int)
      - event_type (str)
      - event_detail (dict|str, optional)
      - ip_address (str, optional)
      - user_agent (str, optional)
    """
    import json
    url = f"{BASE}/user_events"
    resp = requests.post(url, headers=HEADERS, data=json.dumps(data))
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"User event insert failed: {resp.status_code} {resp.text}")
    return resp.json()

# -----------------------------
# Jobs
# -----------------------------

def list_jobs_api(
    *,
    q: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    token: str | None = None,
    select: str = "*",
    order: str = "created_at.desc,id.desc",
    filters: dict[str, str] | None = None,
):
    assert page >= 1 and page_size > 0
    offset = (page - 1) * page_size
    params = {
        "select": select,
        "order": order,
        "limit": str(page_size),
        "offset": str(offset),
    }
    if status:
        params["status"] = f"eq.{status}"
    if q:
        params["or"] = f"(title.ilike.*{q}*,description.ilike.*{q}*)"
    if filters:
        params.update(filters)

    headers = _headers(token, extra={"Prefer": "count=exact"})
    r = requests.get(f"{BASE}/jobs", params=params, headers=headers, timeout=10)
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.reason} :: {r.text}")
    rows = r.json()
    total = None
    cr = r.headers.get("Content-Range")
    if cr and "/" in cr:
        try:
            total = int(cr.split("/")[-1])
        except ValueError:
            total = None
    return rows, total

def get_job_api(job_id: int, *, token: str | None = None, select: str = "*"):
    r = requests.get(
        f"{BASE}/jobs",
        params={"id": f"eq.{job_id}", "select": select, "limit": "1"},
        headers=_headers(token),
        timeout=10,
    )
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.reason} :: {r.text}")
    rows = r.json()
    return rows[0] if rows else None

def create_job_api(payload: dict, *, token: str | None = None):
    r = requests.post(
        f"{BASE}/jobs",
        json=payload,
        headers=_headers(token, extra=HEADERS),
        timeout=10,
    )
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.reason} :: {r.text}")
    data = r.json()
    return data[0] if isinstance(data, list) and data else data

def update_job_api(job_id: int, payload: dict, *, token: str | None = None):
    r = requests.patch(
        f"{BASE}/jobs",
        params={"id": f"eq.{job_id}"},
        json=payload,
        headers=_headers(token, extra=HEADERS),
        timeout=10,
    )
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.reason} :: {r.text}")
    data = r.json()
    return data[0] if isinstance(data, list) and data else data

def delete_job_api(job_id: int, *, token: str | None = None):
    r = requests.delete(
        f"{BASE}/jobs",
        params={"id": f"eq.{job_id}"},
        headers=_headers(token, {"Prefer": "return=representation"}),
        timeout=10,
    )
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.reason} :: {r.text}")
    data = r.json()
    return data[0] if isinstance(data, list) and data else data

# --- Accepted jobs helpers ---

def create_accepted_job(job_id: int, worker_id: int, *, token: str | None = None):
    """
    Insert into accepted_jobs. If the (job_id, worker_id) already exists (409),
    we fetch and return the existing row. Returns a row dict or None.
    """
    url = f"{BASE}/accepted_jobs"

    # Use your existing HEADERS behavior (Prefer: return=representation)
    headers = _headers(token, extra=HEADERS)
    payload = {"job_id": job_id, "worker_id": worker_id}

    r = requests.post(url, json=payload, headers=headers, timeout=10)
    if r.status_code == 409:
        # Unique constraint hit → row already exists; fetch it
        g = requests.get(
            url,
            params={
                "job_id": f"eq.{job_id}",
                "worker_id": f"eq.{worker_id}",
                "limit": "1",
            },
            headers=_headers(token),
            timeout=10,
        )
        if g.ok:
            rows = g.json()
            return rows[0] if rows else None
        return None

    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.reason} :: {r.text}")

    data = r.json()
    return data[0] if isinstance(data, list) and data else data

def list_accepted_jobs(
    worker_id: int,
    *,
    page: int = 1,
    page_size: int = 20,
    order: str = "accepted_at.desc",
    token: str | None = None,
):
    """Return accepted_jobs joined with jobs for a given worker."""
    assert page >= 1 and page_size > 0
    offset = (page - 1) * page_size

    params = {
        "worker_id": f"eq.{worker_id}",
        "select": "id,accepted_at,job:jobs(id,title,category,location,budget,status,created_at)",
        "order": order,
        "limit": str(page_size),
        "offset": str(offset),
    }

    headers = _headers(token, extra={"Prefer": "count=exact"})
    r = requests.get(f"{BASE}/accepted_jobs", params=params, headers=headers, timeout=10)
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.reason} :: {r.text}")

    rows = r.json()
    total = None
    cr = r.headers.get("Content-Range")
    if cr and "/" in cr:
        try:
            total = int(cr.split("/")[-1])
        except ValueError:
            total = None
    return rows, total

# -----------------------------
# Email (SMTP)
# -----------------------------
def send_email(to: str, subject: str, html: str, plain: str | None = None):
    """
    Send an email using SMTP.
    Reads SMTP settings from Flask config:
      MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_USE_TLS
    """
    sender = current_app.config.get("MAIL_USERNAME")
    if not sender:
        raise RuntimeError("MAIL_USERNAME not configured")

    msg = MIMEMultipart("alternative")
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject

    if plain:
        msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(current_app.config.get("MAIL_SERVER"),
                      current_app.config.get("MAIL_PORT")) as server:
        if current_app.config.get("MAIL_USE_TLS"):
            server.starttls()
        if current_app.config.get("MAIL_USERNAME") and current_app.config.get("MAIL_PASSWORD"):
            server.login(
                current_app.config["MAIL_USERNAME"],
                current_app.config["MAIL_PASSWORD"]
            )
        server.sendmail(sender, [to], msg.as_string())
