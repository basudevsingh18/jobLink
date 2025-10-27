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
import os
from datetime import datetime  # kept if you add per-view date helpers later
from typing import Optional

from flask import (
    Blueprint,
    current_app,
    jsonify,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    abort,
)
from urllib.parse import quote_plus
import requests

from . import api
from .common import wa_link, normalize_phone, friendly_datetime, pgrst_base_and_headers

bp = Blueprint("jobs", __name__)

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
# Auth helpers (session-based)
# --------------------------------------------------------------------------------------
def require_login() -> bool:
    if not session.get("user_id"):
        flash("Please log in to continue.", "warning")
        return False
    return True


def require_role(role: str) -> bool:
    if not session.get("user_id"):
        flash("Please log in to continue.", "warning")
        return False
    if (session.get("role") or "").lower() != role.lower():
        flash(f"This action requires a {role} account.", "danger")
        return False
    return True


def require_auth():
    return bool(session.get("user_id"))


def _current_user_id():
    return session.get("user_id") or session.get("uid")


def _is_worker():
    return (session.get("role") or "").lower() == "worker"


# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------
@bp.route("/")
def home():
    return redirect(url_for("jobs.list_jobs"))


@bp.route("/jobs")
def list_jobs():
    q = (request.args.get("q") or "").strip()
    cat = (request.args.get("category") or "").strip()
    loc = (request.args.get("location") or "").strip()
    status  = (request.args.get("status") or "open").strip()
    page = int(request.args.get("page", 1))
    page_size = 20

    filters = {}
    if cat:
        filters["category"] = f"eq.{cat}"
    if loc:
        filters["location"] = f"eq.{loc}"
    if status:
        filters["status"] = f"eq.{status}"

    try:
        rows, total = api.list_jobs_api(
            q=q,
            page=page,
            page_size=page_size,
            select="id,title,description,category,location,budget_cents,created_at,status",
            order="created_at.desc,id.desc",
            filters=filters or None,
        )
    except Exception as e:
        flash(f"Could not load jobs: {e}", "danger")
        rows, total = [], 0

    # facets (always populated)
    categories = api.list_job_categories()
    locations = api.list_job_locations()

    return render_template(
        "jobs/jobs.html",
        jobs=rows,
        total=total or len(rows),
        page=page,
        page_size=page_size,
        q=q,
        cat=cat,
        loc=loc,
        categories=categories,
        locations=locations,
    )


@bp.route("/post-job", methods=["GET", "POST"])
def post_job():
    """
    Authenticated form → creates a job row via PostgREST.
    Dev mode: anon write must be allowed, or use JWT later.
    """
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

    if request.method == "GET":
        return render_template(
            "jobs/post_job.html", categories=CATEGORIES, locations=LOCATIONS
        )

    # POST
    # Read & validate
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    category = (request.form.get("category") or "Other").strip()
    budget_cents_raw = (request.form.get("budget_cents") or "").strip()
    location = (request.form.get("location") or "").strip()
    contact_raw = (request.form.get("contact") or "").strip()
    materials_provided = request.form.get('materials_provided') in ('true', 'on', '1')
    site_visit_required = request.form.get('site_visit_required') in ('true', 'on', '1')
    workmen_required   = request.form.get('workmen_required') in ('true', 'on', '1')

    if not all([title, description, budget_cents_raw, location, contact_raw]):
        flash("Please fill in all required fields.", "warning")
        return render_template(
            "jobs/post_job.html",
            categories=CATEGORIES,
            locations=LOCATIONS,
            form=request.form,
        )

    try:
        budget_cents = int(budget_cents_raw)
        if budget_cents < 0:
            raise ValueError
    except ValueError:
        flash("budget_cents must be a whole number ($).", "warning")
        return render_template(
            "jobs/post_job.html",
            categories=CATEGORIES,
            locations=LOCATIONS,
            form=request.form,
        )

    contact = normalize_phone(contact_raw)
    if not contact:
        flash("Please enter a valid contact number.", "warning")
        return render_template(
            "jobs/post_job.html",
            categories=CATEGORIES,
            locations=LOCATIONS,
            form=request.form,
        )

    payload = {
        "title": title,
        "description": description,
        "category": category,
        "budget_cents": budget_cents,
        "location": location,
        "contact": contact,
        "status": "open",
        # Set from session (RLS/JWT could enforce later)
        "poster_id": session.get("user_id"),
        "materials_provided": materials_provided,
        "site_visit_required": site_visit_required,
        "workmen_required": workmen_required,
    }

    try:
        created_row = api.create_job_api(payload)  # returns created row dict
        new_id = created_row["id"]
        flash("Your job was posted!", "success")
        return redirect(url_for("jobs.job_detail", job_id=new_id))
    except Exception as e:
        flash(f"Failed to post job: {e}", "danger")
        return render_template(
            "jobs/post_job.html",
            categories=CATEGORIES,
            locations=LOCATIONS,
            form=request.form,
        )


@bp.route("/job/<int:job_id>")
def job_detail(job_id: int):
    """
    Show job detail + WhatsApp deep link + link to Apply page (applications blueprint).
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
    whatsapp = (
        wa_link(
            contact_norm,
            f"Hi, I saw your task '{title}' on JobLink. I'm interested. Is it still available?",
        )
        if contact_norm
        else None
    )

    budget_cents = job.get("budget_cents")
    budget_cents_display = f"${budget_cents:,}" if isinstance(budget_cents, int) else (budget_cents or "")
    created_at_display = friendly_datetime(job.get("created_at"))

    # Related (best effort)
    related = []
    try:
        cat = (job.get("category") or "").strip()
        if cat:
            rows, _total = api.list_jobs_api(
                q="",
                page=1,
                page_size=5,
                select="id,title,location,budget_cents,created_at",
                order="created_at.desc,id.desc",
                filters={"category": f"eq.{cat}", "id": f"neq.{job_id}"},
            )
            related = rows
    except Exception:
        related = []

    # ✅ Flags for template
    is_worker = (session.get("role") or "").lower() == "worker"
    is_open = (job.get("status") or "").lower() == "open"
    logged_in = bool(session.get("user_id") or session.get("uid"))

    accept_url = url_for("jobs.accept_job", job_id=job_id)
    apply_url = url_for("applications.apply_form", job_id=job_id)  # new blueprint

    has_applied = False
    if session.get("user_id"):
        apps = api.get_applications_for_user(job_id, session["user_id"])
        has_applied = bool(apps)

    return render_template(
        "jobs/job_detail.html",
        job=job,
        whatsapp=whatsapp,
        accept_url=accept_url,
        apply_url=apply_url,
        budget_cents_display=budget_cents_display,
        created_at_display=created_at_display,
        related_jobs=related,
        is_worker=is_worker,
        is_open=is_open,
        logged_in=logged_in,
        has_applied=has_applied,
    )


@bp.post("/jobs/<int:job_id>/accept")
def accept_job(job_id: int):
    user_id = session.get("user_id")
    role = (session.get("role") or "").lower()
    if not user_id or role != "worker":
        flash("Please log in as a worker to accept jobs.", "warning")
        return redirect(url_for("auth.login"))

    base, _headers = pgrst_base_and_headers()
    token = os.environ.get("PGRST_SERVICE_TOKEN", "")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",  # get inserted row back
    }

    try:
        r = requests.post(
            f"{base}/accepted_jobs",
            headers=headers,
            json={"job_id": job_id, "worker_id": user_id},
            timeout=5,
        )
    except requests.RequestException:
        current_app.logger.exception("POST /accepted_jobs failed")
        flash("Could not reach the server to accept the job.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    if r.status_code in (200, 201):
        flash("You have accepted the job!", "success")
        try:
            job = api.get_job_api(job_id)
        except Exception:
            job = None

        if job:
            contact_norm = normalize_phone(job.get("contact", ""))
            title = (job.get("title") or "").strip()
            if contact_norm:
                message = (
                    f"Hi, I saw your task '{title}' on JobLink. I'm interested. "
                    "Is it still available?"
                )
                return redirect(wa_link(contact_norm, message))

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


@bp.route("/my-jobs")
def my_jobs():
    if not require_role("customer"):
        return redirect(url_for("auth.login"))

    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("auth.login"))

    try:
        rows, total = api.list_jobs_api(
            select="id,title,description,category,location,budget_cents,contact,created_at,customer_id",
            order="created_at.desc,id.desc",
            page=int(request.args.get("page", 1)),
            page_size=20,
            token=session.get("jwt"),
            filters={"customer_id": f"eq.{uid}"},  # <-- key line
        )
        jobs = rows
    except Exception as e:
        flash(f"Could not load jobs: {e}", "danger")
        jobs, total = [], 0

    return render_template(
        "jobs/jobs.html",
        jobs=jobs,
        categories=CATEGORIES,
        locations=LOCATIONS,
        q="",
        cat="",
        loc="",
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
    q = (request.args.get("q") or "").strip()
    cat = (request.args.get("category") or "").strip()
    loc = (request.args.get("location") or "").strip()
    status  = (request.args.get("status") or "open").strip()
    view = (request.args.get("view") or "grid").strip()  # grid | list
    sort = (
        request.args.get("sort") or "newest"
    ).strip()  # newest | oldest | budget_cents_hi | budget_cents_lo
    page = int(request.args.get("page", 1))
    page_sz = int(request.args.get("page_size", 18))

    order_map = {
        "newest": "created_at.desc,id.desc",
        "oldest": "created_at.asc,id.asc",
        "budget_cents_hi": "budget_cents.desc,created_at.desc",
        "budget_cents_lo": "budget_cents.asc,created_at.desc",
    }
    order = order_map.get(sort, order_map["newest"])

    # Build PostgREST filters
    filters = {}
    if cat:
        filters["category"] = f"eq.{cat}"
    if loc:
        filters["location"] = f"eq.{loc}"
    if status:
        filters["status"] = f"eq.{status}"

    jobs, total = api.list_jobs_api(
        q=q,
        page=page,
        page_size=page_sz,
        select="id,title,description,category,location,budget_cents,created_at,status",
        order=order,
        filters=filters or None,
    )

    # lightweight facet lists (from current result set; fine for v1)
    categories = sorted({j.get("category") for j in jobs if j.get("category")})
    locations = sorted({j.get("location") for j in jobs if j.get("location")})

    return render_template(
        "jobs/all_jobs.html",
        jobs=jobs,
        total=total or 0,
        page=page,
        page_size=page_sz,
        q=q,
        cat=cat,
        loc=loc,
        status=status,
        sort=sort,
        view=view,
        categories=categories,
        locations=locations,
    )
