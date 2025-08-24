# microjobs/api.py
import os
import requests

PGRST_URL = os.getenv("PGRST_URL", "http://localhost:3000")

def _headers(token=None):
    h = {"Accept": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h

def list_jobs_api(params=None, token=None):
    r = requests.get(f"{PGRST_URL}/jobs", params=params or {}, headers=_headers(token))
    r.raise_for_status()
    return r.json()

def get_job_api(job_id, token=None):
    params = {"id": f"eq.{job_id}", "select": "id,title,description,category,location,budget,contact,created_at"}
    r = requests.get(f"{PGRST_URL}/jobs", params=params, headers=_headers(token))
    r.raise_for_status()
    data = r.json()
    return data[0] if data else None

def create_job_api(job: dict, token=None):
    # PostgREST returns created row(s) when you POST JSON
    r = requests.post(f"{PGRST_URL}/jobs", json=job, headers={**_headers(token), "Content-Type": "application/json"})
    r.raise_for_status()
    rows = r.json()
    if not rows:
        raise RuntimeError("No row returned from insert")
    return rows[0]
