# microjobs/api.py
import os
import requests

PGRST_URL = os.getenv("PGRST_URL", "http://localhost:3000")

def _headers(token=None):
    h = {"Accept": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h

def get_user_by_email(email: str, token=None):
    # Ask only for what we need; include password_hash for dev login
    params = {
        "email": f"eq.{email}",
        "select": "id,name,email,role,password_hash",
        "limit": 1,
    }
    r = requests.get(f"{PGRST_URL}/users", params=params, headers=_headers(token))
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None

def create_user(payload: dict, token=None):
    # payload should include: name, email, role, password_hash
    r = requests.post(
        f"{PGRST_URL}/users",
        json=payload,
        headers={**_headers(token), "Content-Type": "application/json"},
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None

# (Existing job helpers would be here too)
