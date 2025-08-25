# microjobs/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from urllib.parse import quote_plus
from datetime import datetime
from . import api
bp = Blueprint("jobs", __name__)

JOBS = []
ACCEPTED_JOBS = []
NEXT_ID = 1
NEXT_ACCEPT_ID = 1

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

# --------------------
# Helpers
# --------------------
def wa_link(phone: str, message: str):
    """Generate WhatsApp deep link with message prefilled."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits and not digits.startswith("592"):
        digits = "592" + digits
    return f"https://wa.me/{digits}?text={quote_plus(message)}"

def require_login():
    if not session.get("user_id"):
        flash("Please log in to continue.", "warning")
        return False
    return True

def require_role(role: str):
    if not session.get("user_id"):
        flash("Please log in to continue.", "warning")
        return False
    if session.get("role") != role:
        flash(f"This action requires a {role} account.", "danger")
        return False
    return True

# --------------------
# Routes
# --------------------

@bp.route("/")
def home():
    return redirect(url_for("jobs.list_jobs"))

@bp.route("/jobs")
def list_jobs():
    """
    Fetch from PostgREST with optional filters:
    - q: search in title OR description (ILIKE)
    - category: exact match
    - location: exact match
    Sorted newest-first by created_at (if present).
    """
    q = request.args.get("q", "").strip()
    cat = request.args.get("category", "").strip()
    loc = request.args.get("location", "").strip()

    # Build PostgREST query params
    params = {}

    # Return selected columns explicitly (safer if table evolves)
    params["select"] = "id,title,description,category,location,budget,contact,created_at"

    # Filters
    if q:
        # or=() syntax with ilike wildcards
        params["or"] = f"(title.ilike.*{q}*,description.ilike.*{q}*)"
    if cat:
        params["category"] = f"eq.{cat}"
    if loc:
        params["location"] = f"eq.{loc}"

    # Order newest first (created_at desc if column exists; id desc as fallback)
    params["order"] = "created_at.desc,id.desc"

    try:
        jobs = api.list_jobs_api(params=params)
    except Exception as e:
        flash(f"Could not load jobs: {e}", "danger")
        jobs = []

    return render_template(
        "jobs.html",
        jobs=jobs,
        categories=CATEGORIES,
        locations=LOCATIONS,
        q=q, cat=cat, loc=loc
    )

@bp.route("/post-job", methods=["GET", "POST"])
def post_job():
    # helper: normalize a GY phone for WhatsApp / storage
    def _normalize_phone(raw: str) -> str | None:
        digits = "".join(ch for ch in (raw or "") if ch.isdigit())
        if not digits:
            return None
        # If 7-digit local, prefix 592
        if len(digits) == 7:
            digits = "592" + digits
        return digits

    if request.method == "GET":
        if not require_role("customer"):
            return redirect(url_for("auth.login"))
        return render_template("post_job.html", categories=CATEGORIES, locations=LOCATIONS)

    # POST
    if not require_role("customer"):
        return redirect(url_for("auth.login"))

    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    category = (request.form.get("category") or "Other").strip()
    budget_raw = (request.form.get("budget") or "").strip()
    location = (request.form.get("location") or "").strip()
    contact_raw = (request.form.get("contact") or "").strip()

    # Basic presence validation
    if not all([title, description, budget_raw, location, contact_raw]):
        flash("Please fill in all required fields.", "warning")
        return render_template("post_job.html",
                               categories=CATEGORIES, locations=LOCATIONS,
                               form=request.form)

    # Budget must be an integer >= 0
    try:
        budget = int(budget_raw)
        if budget < 0:
            raise ValueError
    except ValueError:
        flash("Budget must be a whole number (G$).", "warning")
        return render_template("post_job.html",
                               categories=CATEGORIES, locations=LOCATIONS,
                               form=request.form)

    # Normalize contact number
    contact = _normalize_phone(contact_raw)
    if not contact:
        flash("Please enter a valid contact number.", "warning")
        return render_template("post_job.html",
                               categories=CATEGORIES, locations=LOCATIONS,
                               form=request.form)

    # Build payload for PostgREST
    payload = {
        "title": title,
        "description": description,
        "category": category,
        "budget": budget,
        "location": location,
        "contact": contact,
        # include ownership so we can support /my-jobs later via RLS/JWT
        "customer_id": session.get("user_id"),
        "status": "open",
    }

    try:
        created_row = api.create_job_api(payload)  # returns created row dict
        new_id = created_row["id"]
        flash("Your job was posted!", "success")
        return redirect(url_for("jobs.job_detail", job_id=new_id))
    except Exception as e:
        # Common causes: PostgREST permissions (INSERT not allowed),
        # missing columns, or connectivity.
        flash(f"Failed to post job: {e}", "danger")
        return render_template("post_job.html",
                               categories=CATEGORIES, locations=LOCATIONS,
                               form=request.form)

@bp.route("/job/<int:job_id>")
def job_detail(job_id):
    # helpers
    def _normalize_phone(raw: str) -> str | None:
        digits = "".join(ch for ch in (raw or "") if ch.isdigit())
        if not digits:
            return None
        if len(digits) == 7:
            digits = "592" + digits
        return digits

    try:
        job = api.get_job_api(job_id)
    except Exception as e:
        job = None
        flash(f"Error loading job: {e}", "danger")

    if not job:
        flash("Job not found.", "danger")
        return redirect(url_for("jobs.list_jobs"))

    # Safe fields
    title = job.get("title", "").strip()
    contact = _normalize_phone(job.get("contact", ""))
    budget = job.get("budget")
    created_at = job.get("created_at")  # ISO string from PostgREST; show raw for now

    # WhatsApp link (only if we have a valid contact)
    msg = f"Hi, I saw your task '{title}' on JobLink. I'm interested. Is it still available?"
    whatsapp = wa_link(contact, msg) if contact else None

    # Keep accept URL for later (when accepted_jobs logging is wired)
    accept_url = url_for("jobs.accept_job", job_id=job_id)

    # Try to load a few related jobs by category (exclude current)
    related = []
    try:
        cat = (job.get("category") or "").strip()
        if cat:
            params = {
                "select": "id,title,location,budget,created_at",
                "category": f"eq.{cat}",
                "id": f"neq.{job_id}",
                "order": "created_at.desc,id.desc",
                "limit": 5,
            }
            related = list_jobs_api(params=params)
    except Exception:
        related = []

    # Friendly budget (optional)
    budget_display = f"G${budget:,}" if isinstance(budget, int) else (budget or "")

    return render_template(
        "job_detail.html",
        job=job,
        whatsapp=whatsapp,          # None if no contact → template can hide button
        accept_url=accept_url,
        budget_display=budget_display,
        created_at_display=created_at,
        related_jobs=related,       # show a small list/cards if available
    )


@bp.route("/job/<int:job_id>/accept")
def accept_job(job_id):
    """
    Current minimal API mode:
    - Require worker login (UX).
    - Redirect to WhatsApp without server-side logging (until accepted_jobs table & JWT are added).
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

    msg = f"Hi, I saw your task '{job.get('title','')}' on JobLink. I'm interested. Is it still available?"
    whatsapp = wa_link(job.get("contact", ""), msg)
    flash("Opening WhatsApp…", "info")
    return redirect(whatsapp)

@bp.route("/my-jobs")
def my_jobs():
    """
    Placeholder in API-only (anon) mode:
    Without a customer_id column + JWT/RLS, we can’t query ownership.
    Show a friendly note for now.
    """
    if not require_role("customer"):
        return redirect(url_for("auth.login"))
    flash("My Jobs requires account-linked posting. Coming soon with API auth.", "info")
    # Show all jobs as a fallback (or filter by location/category if desired)
    try:
        jobs = list_jobs_api(params={"select": "id,title,description,category,location,budget,contact,created_at",
                                     "order": "created_at.desc,id.desc"})
    except Exception:
        jobs = []
    return render_template("jobs.html", jobs=jobs, categories=CATEGORIES, locations=LOCATIONS, q="", cat="", loc="")

@bp.route("/admin")
def admin():
    # Minimal: just list jobs newest-first
    try:
        jobs = list_jobs_api(params={"select": "id,title,description,category,location,budget,contact,created_at",
                                     "order": "created_at.desc,id.desc"})
    except Exception as e:
        flash(f"Could not load admin list: {e}", "danger")
        jobs = []
    return render_template("admin.html", jobs=jobs)

@bp.route("/seed")
def seed():
    """
    With PostgREST, seeding should be done by SQL in db/init/*.sql on first boot.
    Keep this endpoint to avoid breaking links; just inform the user.
    """
    flash("Seeding is handled by the database on first startup.", "info")
    return redirect(url_for("jobs.list_jobs"))
