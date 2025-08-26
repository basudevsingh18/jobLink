# microjobs/api.py
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import smtplib
from flask import current_app
import requests

# PGRST_URL = os.getenv("PGRST_URL", "http://localhost:3000")
BASE = "http://localhost:3000" 
HEADERS = {
    "Content-Type": "application/json",
    # This makes PostgREST return the inserted row(s) as JSON
    "Prefer": "return=representation"
}

def _headers(token=None, extra: dict | None = None):
    h = {"Accept": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if extra:
        h.update(extra)
    return h

def get_user_by_email(email: str):
    # GET /users?email=eq.someone@example.com
    r = requests.get(f"{BASE}/users", params={"email": f"eq.{email}"}, timeout=10)
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.reason} :: {r.text}")
    rows = r.json()
    return rows[0] if rows else None

def create_user(payload: dict):
    resp = requests.post(f"{BASE}/users", json=payload, headers=HEADERS, timeout=10)
    if not resp.ok:
        # Bubble up details so your flash() shows something helpful
        raise RuntimeError(f"{resp.status_code} {resp.reason} :: {resp.text}")

    # With return=representation, body is a JSON array of created rows
    data = resp.json()
    if isinstance(data, list) and data:
        return data[0]  # first created row
    elif isinstance(data, dict):
        return data
    else:
        # Extremely defensive; shouldn't happen with return=representation
        raise RuntimeError("Create succeeded but response body was not a row.")

# ---------- JOBS ----------
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
        try: total = int(cr.split("/")[-1])
        except ValueError: total = None
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
    # PostgREST returns deleted row(s) if Prefer=return=representation
    data = r.json()
    return data[0] if isinstance(data, list) and data else data

# def send_email(to: str, subject: str, html: str, plain: str | None = None):
    """
    Send an email using SMTP.
    Reads SMTP settings from Flask config:
      MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_USE_TLS/SSL
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
