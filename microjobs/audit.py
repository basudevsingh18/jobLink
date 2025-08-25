# microjobs/audit.py
from microjobs import api
from flask import request

def log_event(user_id: int, event_type: str, detail: dict | None = None):
    api.create_user_event({
        "user_id": user_id,
        "event_type": event_type,
        "event_detail": detail or {},
        "ip_address": request.remote_addr if request else None,
        "user_agent": request.headers.get("User-Agent") if request else None
    })
