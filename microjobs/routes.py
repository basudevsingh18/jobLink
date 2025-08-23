# microjobs/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from urllib.parse import quote_plus
from datetime import datetime

bp = Blueprint("jobs", __name__)

# --------------------
# In-memory stores (replace with DB later)
# --------------------
JOBS = []
NEXT_ID = 1

# Track worker acceptances
ACCEPTED_JOBS = []  # [{id, job_id, worker_id, accepted_at}]
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
    q = request.args.get("q", "").strip().lower()
    cat = request.args.get("category", "").strip()
    loc = request.args.get("location", "").strip()

    filtered = [j for j in JOBS if j["status"] == "open"]

    if q:
        filtered = [j for j in filtered if q in j["title"].lower() or q in j["description"].lower()]
    if cat:
        filtered = [j for j in filtered if j["category"] == cat]
    if loc:
        filtered = [j for j in filtered if j["location"] == loc]

    filtered = sorted(filtered, key=lambda x: x["created_at"], reverse=True)

    return render_template(
        "jobs.html",
        jobs=filtered,
        categories=CATEGORIES,
        locations=LOCATIONS,
        q=q, cat=cat, loc=loc
    )

@bp.route("/post-job", methods=["GET", "POST"])
def post_job():
    # Only logged-in CUSTOMERS can post
    if request.method == "GET":
        if not require_role("customer"):
            return redirect(url_for("auth.login"))
        return render_template("post_job.html", categories=CATEGORIES, locations=LOCATIONS)

    # POST
    if not require_role("customer"):
        return redirect(url_for("auth.login"))

    global NEXT_ID
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    category = request.form.get("category", "").strip()
    budget = request.form.get("budget", "").strip()
    location = request.form.get("location", "").strip()
    contact = request.form.get("contact", "").strip()

    if not (title and description and budget and location and contact):
        flash("Please fill in all required fields.", "warning")
        return render_template("post_job.html", categories=CATEGORIES, locations=LOCATIONS)

    job = {
        "id": NEXT_ID,
        "title": title,
        "description": description,
        "category": category or "Other",
        "budget": budget,
        "location": location,
        "contact": contact,
        "status": "open",
        "created_at": datetime.now(),
        # ownership
        "customer_id": session.get("user_id"),
        "customer_name": session.get("user_name"),
        "customer_email": session.get("user_email") if session.get("user_email") else None,
    }
    JOBS.append(job)
    NEXT_ID += 1
    flash("Your job was posted!", "success")
    return redirect(url_for("jobs.job_detail", job_id=job["id"]))

@bp.route("/job/<int:job_id>")
def job_detail(job_id):
    job = next((j for j in JOBS if j["id"] == job_id), None)
    if not job:
        flash("Job not found.", "danger")
        return redirect(url_for("jobs.list_jobs"))

    msg = f"Hi, I saw your task '{job['title']}' on JobLink. I'm interested. Is it still available?"
    whatsapp = wa_link(job["contact"], msg)

    # accept_url lets us log acceptance (for workers) before redirecting to WhatsApp
    accept_url = url_for("jobs.accept_job", job_id=job_id)

    return render_template("job_detail.html", job=job, whatsapp=whatsapp, accept_url=accept_url)

@bp.route("/job/<int:job_id>/accept")
def accept_job(job_id):
    """Worker-only: log acceptance then send them to WhatsApp link."""
    # require worker login
    if not require_role("worker"):
        return redirect(url_for("auth.login"))

    job = next((j for j in JOBS if j["id"] == job_id), None)
    if not job:
        flash("Job not found.", "danger")
        return redirect(url_for("jobs.list_jobs"))

    # log acceptance
    global NEXT_ACCEPT_ID
    ACCEPTED_JOBS.append({
        "id": NEXT_ACCEPT_ID,
        "job_id": job_id,
        "worker_id": session.get("user_id"),
        "accepted_at": datetime.now()
    })
    NEXT_ACCEPT_ID += 1

    # build WA link and redirect
    msg = f"Hi, I saw your task '{job['title']}' on JobLink. I'm interested. Is it still available?"
    whatsapp = wa_link(job["contact"], msg)

    flash("Acceptance recorded. Opening WhatsApp…", "info")
    return redirect(whatsapp)

@bp.route("/my-jobs")
def my_jobs():
    """Customer dashboard: list only jobs posted by the logged-in customer."""
    if not require_role("customer"):
        return redirect(url_for("auth.login"))

    uid = session.get("user_id")
    mine = [j for j in JOBS if j.get("customer_id") == uid]
    mine = sorted(mine, key=lambda x: x["created_at"], reverse=True)

    return render_template("jobs.html", jobs=mine, categories=CATEGORIES, locations=LOCATIONS, q="", cat="", loc="")

@bp.route("/admin")
def admin():
    # Optionally: restrict to admin role later
    all_jobs = sorted(JOBS, key=lambda x: x["created_at"], reverse=True)
    return render_template("admin.html", jobs=all_jobs)

@bp.route("/seed")
def seed():
    """Seed demo jobs for quick testing."""
    global NEXT_ID, JOBS, ACCEPTED_JOBS, NEXT_ACCEPT_ID
    JOBS.clear()
    ACCEPTED_JOBS.clear()
    NEXT_ID = 1
    NEXT_ACCEPT_ID = 1
    samples = [
        {"title": "Install ceiling fan", "description": "Need a fan installed, wire ready.", "category": "Electrical", "budget": "6000", "location": "Georgetown", "contact": "6001234"},
        {"title": "Math tutor for CSEC", "description": "After-school sessions, 2x per week.", "category": "Tutoring", "budget": "8000", "location": "Linden", "contact": "6448888"},
        {"title": "Fix leaking pipe", "description": "Small leak under kitchen sink.", "category": "Plumbing", "budget": "5000", "location": "East Coast Demerara", "contact": "6152222"},
    ]
    now = datetime.now()
    # If logged-in customer seeds, assign ownership to them; else None
    cid = session.get("user_id")
    cname = session.get("user_name")
    for s in samples:
        JOBS.append({
            "id": NEXT_ID,
            **s,
            "status": "open",
            "created_at": now,
            "customer_id": cid,
            "customer_name": cname,
            "customer_email": session.get("user_email") if session.get("user_email") else None,
        })
        NEXT_ID += 1
    flash("Seeded demo jobs.", "info")
    return redirect(url_for("jobs.list_jobs"))
