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

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from urllib.parse import quote_plus
from datetime import datetime
from typing import Optional
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

# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------
@bp.route("/")
def home():
    return redirect(url_for("jobs.list_jobs"))

@bp.route("/jobs")
def list_jobs():
    page = int(request.args.get("page", 1))
    q = request.args.get("q") or None
    status = request.args.get("status") or None

    try:
        rows, total = api.list_jobs_api(q=q, status=status, page=page, page_size=20)
    except Exception as e:
        flash(f"Could not load jobs: {e}", "danger")
        return render_template("jobs.html", jobs=[], total=0, page=page)

    return render_template("jobs.html", jobs=rows, total=total or len(rows), page=page)

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
    Show job detail + WhatsApp deep link.
    Also fetch a few related jobs (same category) if available.
    """
    try:
        job = api.get_job_api(job_id)
    except Exception as e:
        job = None
        flash(f"Error loading job: {e}", "danger")

    if not job:
        flash("Job not found.", "danger")
        return redirect(url_for("jobs.list_jobs"))

    # Precompute display fields
    title = (job.get("title") or "").strip()
    contact_norm = normalize_phone(job.get("contact", ""))
    whatsapp = wa_link(contact_norm, f"Hi, I saw your task '{title}' on JobLink. I'm interested. Is it still available?") if contact_norm else None
    budget = job.get("budget")
    budget_display = f"G${budget:,}" if isinstance(budget, int) else (budget or "")
    created_at_display = friendly_datetime(job.get("created_at"))

    # Related jobs (best-effort; ignore errors)
    related = []
    try:
        cat = (job.get("category") or "").strip()
        if cat:
            related = api.list_jobs_api(params={
                "select": "id,title,location,budget,created_at",
                "category": f"eq.{cat}",
                "id": f"neq.{job_id}",
                "order": "created_at.desc,id.desc",
                "limit": 5,
            })
    except Exception:
        related = []

    # Keep accept URL (will log to DB later when accepted_jobs is ready)
    accept_url = url_for("jobs.accept_job", job_id=job_id)

    return render_template(
        "job_detail.html",
        job=job,
        whatsapp=whatsapp,                # None → template can hide the button
        accept_url=accept_url,
        budget_display=budget_display,
        created_at_display=created_at_display,
        related_jobs=related,
    )

@bp.route("/job/<int:job_id>/accept")
def accept_job(job_id: int):
    """
    Worker-only accept flow.
    For now: just open WhatsApp; DB logging will come with accepted_jobs + JWT.
    """
    if not require_role("worker"):
        return redirect(url_for("auth.login"))

    job = None
    try:
        job = api.get_job_api(job_id)
    except Exception:
        pass

    if not job:
        flash("Job not found.", "danger")
        return redirect(url_for("jobs.list_jobs"))

    whatsapp = wa_link(
        normalize_phone(job.get("contact", "")) or "",
        f"Hi, I saw your task '{job.get('title','')}' on JobLink. I'm interested. Is it still available?",
    )
    flash("Opening WhatsApp…", "info")
    return redirect(whatsapp)

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
