# microjobs/routes.py
"""
Job routes (Flask) backed by PostgREST.

- Lists/searches jobs with optional filters.
- Posts a job (customer-only) via PostgREST.
- Shows job detail with a WhatsApp deep link.
- Accept flow currently just redirects to WhatsApp (logging to DB comes later).
- "My Jobs" placeholder until JWT/RLS + customer_id filtering is enabled.

Notes:
- We import the api MODULE (not functions) so tests can monkeypatch it cleanly.
- PostgREST returns ISO timestamps (strings). We precompute a display string.
"""

from __future__ import annotations
from functools import wraps
from os import abort
import os

from flask import Blueprint, current_app, jsonify, render_template, request, redirect, url_for, flash, session
from urllib.parse import quote_plus
from datetime import datetime
from typing import Optional

import requests
from . import api
from werkzeug.security import generate_password_hash, check_password_hash

bp = Blueprint("jobs", __name__)

# --------------------------------------------------------------------------------------
# Back-compat placeholders (legacy tests may clear these). They are not used by routes.
# --------------------------------------------------------------------------------------
JOBS: list[dict] = []
ACCEPTED_JOBS: list[dict] = []
NEXT_ID: int = 1
NEXT_ACCEPT_ID: int = 1

# --------------------------------------------------------------------------------------
# Static lists feeding dropdowns/filters
# --------------------------------------------------------------------------------------
CATEGORIES = [
    "Home Repairs",
    "Electrical",
    "Plumbing",
    "Cleaning",
    "Tutoring",
    "IT Help",
    "Events",
]

LOCATIONS = [
    "Georgetown",
    "East Bank Demerara",
    "East Coast Demerara",
    "West Demerara",
    "Linden",
    "Berbice",
]

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def wa_link(phone: str, message: str) -> str:
    """Generate WhatsApp deep link with a prefilled message."""
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if digits and not digits.startswith("592"):
        # treat 7-digit local numbers as Guyana numbers and prefix 592
        if len(digits) == 7:
            digits = "592" + digits
    return f"https://wa.me/{digits}?text={quote_plus(message)}"

def normalize_phone(raw: str) -> Optional[str]:
    """Return normalized E.164-ish local number or None if invalid/empty."""
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    if not digits:
        return None
    if len(digits) == 7:
        digits = "592" + digits
    return digits

def friendly_datetime(iso_str: Optional[str]) -> str:
    """Render ISO timestamp strings nicely; return original if parsing fails."""
    if not iso_str:
        return ""
    try:
        # Handle 'Z' and timezone offsets
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y %I:%M %p")
    except Exception:
        return iso_str

def require_login() -> bool:
    if not session.get("user_id"):
        flash("Please log in to continue.", "warning")
        return False
    return True

def require_role(role: str) -> bool:
    if not session.get("user_id"):
        flash("Please log in to continue.", "warning")
        return False
    if session.get("role") != role:
        flash(f"This action requires a {role} account.", "danger")
        return False
    return True

def require_auth():
    return bool(session.get("user_id"))

def _current_user_id():
    return session.get("user_id") or session.get("uid")

def _is_worker():
    return (session.get("role") or "").lower() == "worker"

def worker_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("You must log in first.", "warning")
            return redirect(url_for("account.login"))
        if session.get("role") != "worker":
            flash("Only workers can accept jobs.", "danger")
            return redirect(url_for("jobs.list_jobs"))
        return f(*args, **kwargs)
    return decorated

def _pgrst():
    base = os.environ.get("POSTGREST_URL", "http://localhost:3000")
    token = os.environ.get("PGRST_SERVICE_TOKEN", "")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    return base, headers

# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------
@bp.route("/")
def home():
    return redirect(url_for("jobs.list_jobs"))

@bp.route("/jobs")
def list_jobs():
    q   = (request.args.get("q") or "").strip()
    cat = (request.args.get("category") or "").strip()
    loc = (request.args.get("location") or "").strip()
    page = int(request.args.get("page", 1))
    page_size = 20

    filters = {}
    if cat: filters["category"] = f"eq.{cat}"
    if loc: filters["location"] = f"eq.{loc}"

    try:
        rows, total = api.list_jobs_api(
            q=q, page=page, page_size=page_size,
            select="id,title,description,category,location,budget,created_at,status",
            order="created_at.desc,id.desc",
            filters=filters or None,
        )
    except Exception as e:
        flash(f"Could not load jobs: {e}", "danger")
        rows, total = [], 0

    # facets (always populated)
    categories = api.list_job_categories()
    locations  = api.list_job_locations()

    return render_template(
        "jobs.html",
        jobs=rows, total=total or len(rows),
        page=page, page_size=page_size,
        q=q, cat=cat, loc=loc,
        categories=categories, locations=locations,
    )

@bp.route("/post-job", methods=["GET", "POST"])
def post_job():
    """
    Customer-only form → creates a job row via PostgREST.
    Dev mode: anon write must be allowed, or use JWT later.
    """
    if request.method == "GET":
        if not require_role("customer"):
            return redirect(url_for("auth.login"))
        return render_template("post_job.html", categories=CATEGORIES, locations=LOCATIONS)

    # POST
    if not require_role("customer"):
        return redirect(url_for("auth.login"))

    # Read & validate
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    category = (request.form.get("category") or "Other").strip()
    budget_raw = (request.form.get("budget") or "").strip()
    location = (request.form.get("location") or "").strip()
    contact_raw = (request.form.get("contact") or "").strip()

    if not all([title, description, budget_raw, location, contact_raw]):
        flash("Please fill in all required fields.", "warning")
        return render_template("post_job.html",
                               categories=CATEGORIES, locations=LOCATIONS,
                               form=request.form)

    try:
        budget = int(budget_raw)
        if budget < 0:
            raise ValueError
    except ValueError:
        flash("Budget must be a whole number (G$).", "warning")
        return render_template("post_job.html",
                               categories=CATEGORIES, locations=LOCATIONS,
                               form=request.form)

    contact = normalize_phone(contact_raw)
    if not contact:
        flash("Please enter a valid contact number.", "warning")
        return render_template("post_job.html",
                               categories=CATEGORIES, locations=LOCATIONS,
                               form=request.form)

    payload = {
        "title": title,
        "description": description,
        "category": category,
        "budget": budget,
        "location": location,
        "contact": contact,
        "status": "open",
        # When JWT/RLS is enabled, this will be set server-side from JWT claims.
        "customer_id": session.get("user_id"),
    }

    try:
        created_row = api.create_job_api(payload)  # returns created row dict
        new_id = created_row["id"]
        flash("Your job was posted!", "success")
        return redirect(url_for("jobs.job_detail", job_id=new_id))
    except Exception as e:
        flash(f"Failed to post job: {e}", "danger")
        return render_template("post_job.html",
                               categories=CATEGORIES, locations=LOCATIONS,
                               form=request.form)

@bp.route("/job/<int:job_id>")
def job_detail(job_id: int):
    """
    Show job detail + WhatsApp deep link + Apply modal.
    """
    try:
        job = api.get_job_api(job_id)
    except Exception as e:
        job = None
        flash(f"Error loading job: {e}", "danger")

    if not job:
        flash("Job not found.", "danger")
        return redirect(url_for("jobs.list_jobs"))

    # Display helpers
    title = (job.get("title") or "").strip()
    contact_norm = normalize_phone(job.get("contact", ""))
    whatsapp = wa_link(contact_norm, f"Hi, I saw your task '{title}' on JobLink. I'm interested. Is it still available?") if contact_norm else None

    budget = job.get("budget")
    budget_display = f"G${budget:,}" if isinstance(budget, int) else (budget or "")
    created_at_display = friendly_datetime(job.get("created_at"))

    # Related (best effort)
    related = []
    try:
        cat = (job.get("category") or "").strip()
        if cat:
            # adjust to your api.list_jobs_api signature if needed
            rows, _total = api.list_jobs_api(
                q="",
                page=1,
                page_size=5,
                select="id,title,location,budget,created_at",
                order="created_at.desc,id.desc",
                filters={"category": f"eq.{cat}", "id": f"neq.{job_id}"}
            )
            related = rows
    except Exception:
        related = []

    # ✅ Flags for template
    is_worker = (session.get("role") or "").lower() == "worker"
    is_open   = (job.get("status") or "").lower() == "open"
    logged_in = bool(session.get("user_id") or session.get("uid"))

    accept_url = url_for("jobs.accept_job", job_id=job_id)

    return render_template(
        "job_detail.html",
        job=job,
        whatsapp=whatsapp,
        accept_url=accept_url,
        budget_display=budget_display,
        created_at_display=created_at_display,
        related_jobs=related,
        is_worker=is_worker,
        is_open=is_open,
        logged_in=logged_in,
    )

@bp.post("/jobs/<int:job_id>/accept")
def accept_job(job_id: int):
    user_id = session.get("user_id")
    role = session.get("role")
    if not user_id or role != "worker":
        flash("Please log in as a worker to accept jobs.", "warning")
        return redirect(url_for("account.login"))

    base_url = os.environ.get("POSTGREST_URL", "http://localhost:3000")
    token = os.environ.get("PGRST_SERVICE_TOKEN", "")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"  # get inserted row back
    }

    try:
        r = requests.post(
            f"{base_url}/accepted_jobs",
            headers=headers,
            json={"job_id": job_id, "worker_id": user_id},
            timeout=5
        )
    except requests.RequestException:
        current_app.logger.exception("POST /accepted_jobs failed")
        flash("Could not reach the server to accept the job.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    if r.status_code in (200, 201):
        flash("You have accepted the job!", "success")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    # Friendly messages for common cases
    msg = None
    try:
        body = r.json()
        msg = body.get("message") or body.get("hint")
    except Exception:
        pass

    if r.status_code == 409:
        flash("This job has already been accepted by someone else.", "warning")
    elif r.status_code == 400:
        flash(msg or "Job cannot be accepted in its current state.", "warning")
    elif r.status_code in (401, 403):
        flash("Not authorized to accept jobs.", "danger")
    else:
        flash(f"Server error while accepting job (HTTP {r.status_code}).", "danger")

    return redirect(url_for("jobs.job_detail", job_id=job_id))

@bp.post("/jobs/<int:job_id>/apply", endpoint="apply_to_job")
def apply_to_job(job_id: int):
    user_id = session.get("user_id")
    role = (session.get("role") or "").lower()
    if not user_id or role != "worker":
        flash("Please log in as a worker to apply.", "warning")
        return redirect(url_for("auth.login", next=request.path))

    base, headers = _pgrst()

    proposal = request.form.get("proposal") or None
    bid_cents = request.form.get("bid_cents") or None
    days     = request.form.get("days_to_complete") or None

    payload = {
        "job_id": job_id,
        "worker_id": user_id,
        "proposal": proposal,
        "bid_cents": int(bid_cents) if bid_cents else None,
        "days_to_complete": int(days) if days else None,
    }

    def _post_to(path):
        return requests.post(
            f"{base}/{path}",
            headers={**headers, "Prefer": "return=representation"},
            json=payload,
            timeout=6
        )

    try:
        # try plural first (most common), then singular
        r = _post_to("job_applications")
        if r.status_code == 404:
            r = _post_to("job_applications")
    except requests.RequestException:
        current_app.logger.exception("POST to PostgREST failed")
        flash("Network error reaching the database API.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    if r.status_code in (200, 201):
        flash("Application submitted!", "success")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    # Show more helpful error info
    msg = None
    try:
        body = r.json()
        msg = body.get("message") or body.get("hint") or body
    except Exception:
        msg = r.text or None

    if r.status_code == 409:
        flash("You already applied for this job.", "info")
    elif r.status_code in (401, 403):
        flash("Not authorized to apply. (401/403 from PostgREST)", "danger")
    elif r.status_code == 404:
        flash(f"PostgREST 404: endpoint not found at {base}/job_applications. Check table name & exposed schemas. Details: {msg}", "danger")
    else:
        flash(f"Could not submit application (HTTP {r.status_code}). Details: {msg}", "danger")

    return redirect(url_for("jobs.job_detail", job_id=job_id))


@bp.get("/jobs/<int:job_id>/applications", endpoint="list_applications")
def list_applications(job_id: int):
    # TODO: authorize that the current user owns this job or is admin
    # owner_id = session.get("user_id")

    base, headers = _pgrst()
    # Get the job (so you can show title/owner) and the applications
    job_r = requests.get(f"{base}/jobs?id=eq.{job_id}", headers=headers, timeout=5)
    job = job_r.json()[0] if job_r.status_code == 200 and job_r.json() else None

    apps_r = requests.get(
        f"{base}/job_applications?job_id=eq.{job_id}&order=created_at.asc",
        headers=headers, timeout=5
    )
    applications = apps_r.json() if apps_r.status_code == 200 else []

    return render_template("jobs/applications.html", job=job, applications=applications)

@bp.post("/jobs/<int:job_id>/applications/<int:app_id>/accept", endpoint="accept_application")
def accept_application(job_id: int, app_id: int):
    # TODO: authorize the current user owns this job (customer)
    base, headers = _pgrst()

    try:
        r = requests.patch(
            f"{base}/job_applications?id=eq.{app_id}&job_id=eq.{job_id}",
            headers=headers,
            json={"status": "accepted"},
            timeout=5
        )
    except requests.RequestException:
        current_app.logger.exception("PATCH /job_applications accept failed")
        flash("Could not accept application (network).", "danger")
        return redirect(url_for("jobs.list_applications", job_id=job_id))

    if r.status_code in (200, 204):
        flash("Application accepted. Others auto-declined.", "success")
    else:
        msg = None
        try:
            msg = r.json().get("message") or r.json().get("hint")
        except Exception:
            pass
        flash(msg or f"Could not accept application (HTTP {r.status_code}).", "danger")

    return redirect(url_for("jobs.list_applications", job_id=job_id))

@bp.post("/jobs/<int:job_id>/applications/<int:app_id>/decline", endpoint="decline_application")
def decline_application(job_id: int, app_id: int):
    # TODO: authorize customer
    base, headers = _pgrst()
    try:
        r = requests.patch(
            f"{base}/job_applications?id=eq.{app_id}&job_id=eq.{job_id}",
            headers=headers,
            json={"status": "declined"},
            timeout=5
        )
    except requests.RequestException:
        current_app.logger.exception("PATCH /job_applications decline failed")
        flash("Could not decline application (network).", "danger")
        return redirect(url_for("jobs.list_applications", job_id=job_id))

    if r.status_code in (200, 204):
        flash("Application declined.", "info")
    else:
        msg = None
        try:
            msg = r.json().get("message") or r.json().get("hint")
        except Exception:
            pass
        flash(msg or f"Could not decline application (HTTP {r.status_code}).", "danger")

    return redirect(url_for("jobs.list_applications", job_id=job_id))

@bp.post("/jobs/<int:job_id>/applications/<int:app_id>/withdraw", endpoint="withdraw_application")
def withdraw_application(job_id: int, app_id: int):
    user_id = session.get("user_id")
    role = session.get("role")
    if not user_id or role != "worker":
        flash("Please log in as a worker.", "warning")
        return redirect(url_for("auth.login", next=request.path))

    base, headers = _pgrst()
    # Ensure it's their application (enforce via PostgREST RLS or by fetching first)
    try:
        r = requests.patch(
            f"{base}/job_applications?id=eq.{app_id}&job_id=eq.{job_id}&worker_id=eq.{user_id}",
            headers=headers,
            json={"status": "withdrawn"},
            timeout=5
        )
    except requests.RequestException:
        current_app.logger.exception("PATCH /job_applications withdraw failed")
        flash("Could not withdraw application (network).", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    if r.status_code in (200, 204):
        flash("Application withdrawn.", "info")
    else:
        msg = None
        try:
            msg = r.json().get("message") or r.json().get("hint")
        except Exception:
            pass
        flash(msg or f"Could not withdraw application (HTTP {r.status_code}).", "danger")

    return redirect(url_for("jobs.job_detail", job_id=job_id))

@bp.get("/jobs/<int:job_id>/apply", endpoint="apply_form")
def apply_form(job_id: int):
    # Must be a logged-in worker
    user_id = session.get("user_id")
    role = (session.get("role") or "").lower()

    if not user_id or role != "worker":
        flash("Please log in as a worker to apply.", "warning")
        return redirect(url_for("auth.login", next=request.path))

    # Load job to display on the page
    try:
        job = api.get_job_api(job_id)
        if not job:
            flash("Job not found.", "danger")
            return redirect(url_for("jobs.list_jobs"))
    except Exception as e:
        flash(f"Error loading job: {e}", "danger")
        return redirect(url_for("jobs.list_jobs"))

    # Must be open
    if (job.get("status") or "").lower() != "open":
        flash("This job is not open for applications.", "warning")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    # Nice display bits
    budget = job.get("budget")
    budget_display = f"G${budget:,}" if isinstance(budget, int) else (budget or "")
    created_at_display = friendly_datetime(job.get("created_at"))

    return render_template(
        "jobs/apply.html",
        job=job,
        budget_display=budget_display,
        created_at_display=created_at_display,
    )



@bp.route("/my-jobs")
def my_jobs():
    if not require_role("customer"):
        return redirect(url_for("auth.login"))

    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("auth.login"))

    try:
        rows, total = api.list_jobs_api(
            select="id,title,description,category,location,budget,contact,created_at,customer_id",
            order="created_at.desc,id.desc",
            page=int(request.args.get("page", 1)),
            page_size=20,
            token=session.get("jwt"),
            filters={"customer_id": f"eq.{uid}"}  # <-- key line
        )
        jobs = rows
    except Exception as e:
        flash(f"Could not load jobs: {e}", "danger")
        jobs, total = [], 0

    return render_template(
        "jobs.html",
        jobs=jobs,
        categories=CATEGORIES,
        locations=LOCATIONS,
        q="", cat="", loc="",
        total=total or len(jobs),
        page=int(request.args.get("page", 1)),
    )

@bp.route("/seed")
def seed():
    """
    Seeding is handled by SQL in db/init/*.sql on first DB startup.
    Keep endpoint for UX continuity.
    """
    flash("Seeding is handled by the database on first startup.", "info")
    return redirect(url_for("jobs.list_jobs"))

@bp.route("/all")
def all_jobs():
    q       = (request.args.get("q") or "").strip()
    cat     = (request.args.get("category") or "").strip()
    loc     = (request.args.get("location") or "").strip()
    status  = (request.args.get("status") or "").strip()
    view    = (request.args.get("view") or "grid").strip()   # grid | list
    sort    = (request.args.get("sort") or "newest").strip() # newest | oldest | budget_hi | budget_lo
    page    = int(request.args.get("page", 1))
    page_sz = int(request.args.get("page_size", 18))

    order_map = {
        "newest":    "created_at.desc,id.desc",
        "oldest":    "created_at.asc,id.asc",
        "budget_hi": "budget.desc,created_at.desc",
        "budget_lo": "budget.asc,created_at.desc",
    }
    order = order_map.get(sort, order_map["newest"])

    # Build PostgREST filters
    filters = {}
    if cat:    filters["category"] = f"eq.{cat}"
    if loc:    filters["location"] = f"eq.{loc}"
    if status: filters["status"]   = f"eq.{status}"

    jobs, total = api.list_jobs_api(
        q=q, page=page, page_size=page_sz,
        select="id,title,description,category,location,budget,created_at,status",
        order=order,
        filters=filters or None
    )

    # lightweight facet lists (from current result set; fine for v1)
    categories = sorted({j.get("category") for j in jobs if j.get("category")})
    locations  = sorted({j.get("location") for j in jobs if j.get("location")})

    return render_template(
        "all_jobs.html",
        jobs=jobs, total=total or 0,
        page=page, page_size=page_sz,
        q=q, cat=cat, loc=loc, status=status,
        sort=sort, view=view,
        categories=categories, locations=locations
    )
