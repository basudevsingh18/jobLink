from __future__ import annotations
import os
from datetime import datetime
from typing import Optional

def wa_link(phone: str, message: str) -> str:
    from urllib.parse import quote_plus
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits and not digits.startswith("592"):
        if len(digits) == 7:
            digits = "592" + digits
    return f"https://wa.me/{digits}?text={quote_plus(message)}"

def normalize_phone(raw: str) -> Optional[str]:
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if not digits:
        return None
    if len(digits) == 7:
        digits = "592" + digits
    return digits

def friendly_datetime(iso_str: Optional[str]) -> str:
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return iso_str

def pgrst_base_and_headers():
    base = os.environ.get("POSTGREST_URL", "http://localhost:3000")
    token = os.environ.get("PGRST_SERVICE_TOKEN", "")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    return base, headers
