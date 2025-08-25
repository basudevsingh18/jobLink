# microjobs/api.py
import os
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
# def list_jobs_api(
#     *,
#     q: str | None = None,
#     status: str | None = None,
#     page: int = 1,
#     page_size: int = 20,
#     token: str | None = None,
#     select: str = "*"  # <-- no hard-coded non-existent columns
# ):
#     """
#     Fetch paginated jobs with optional search and status filter.
#     Returns (rows, total_count or None)
#     """
#     assert page >= 1 and page_size > 0
#     offset = (page - 1) * page_size

#     params = {
#         "select": select,
#         "order": "created_at.desc",
#         "limit": str(page_size),
#         "offset": str(offset),
#     }
#     if status:
#         params["status"] = f"eq.{status}"

#     if q:
#         # Match title or description if they exist; harmless if one is missing
#         params["or"] = f"(title.ilike.*{q}*,description.ilike.*{q}*)"

#     # Prefer exact count in Content-Range
#     headers = _headers(token, extra={"Prefer": "count=exact"})
#     r = requests.get(f"{BASE}/jobs", params=params, headers=headers, timeout=10)

#     if not r.ok:
#         raise RuntimeError(f"{r.status_code} {r.reason} :: {r.text}")

#     rows = r.json()

#     total = None
#     cr = r.headers.get("Content-Range")  # e.g., "0-19/123"
#     if cr and "/" in cr:
#         try:
#             total = int(cr.split("/")[-1])
#         except ValueError:
#             total = None

#     return rows, total


# def list_jobs_api(
#     *,
#     q: str | None = None,
#     status: str | None = None,
#     page: int = 1,
#     page_size: int = 20,
#     token: str | None = None,
#     select: str = "*",
#     order: str = "created_at.desc"
# ):
#     assert page >= 1 and page_size > 0
#     offset = (page - 1) * page_size
#     params = {
#         "select": select,
#         "order": order,
#         "limit": str(page_size),
#         "offset": str(offset),
#     }
#     if status:
#         params["status"] = f"eq.{status}"
#     if q:
#         params["or"] = f"(title.ilike.*{q}*,description.ilike.*{q}*)"

#     headers = _headers(token, extra={"Prefer": "count=exact"})
#     r = requests.get(f"{BASE}/jobs", params=params, headers=headers, timeout=10)
#     if not r.ok:
#         raise RuntimeError(f"{r.status_code} {r.reason} :: {r.text}")

#     rows = r.json()
#     total = None
#     cr = r.headers.get("Content-Range")
#     if cr and "/" in cr:
#         try:
#             total = int(cr.split("/")[-1])
#         except ValueError:
#             total = None
#     return rows, total


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