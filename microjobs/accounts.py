
from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from urllib.parse import quote_plus
from datetime import datetime
from typing import Optional

from microjobs.routes import require_auth
from . import api
from werkzeug.security import generate_password_hash, check_password_hash

bp = Blueprint("account", __name__)

@bp.route("/me")
def me():
    role = (session.get("role") or "").lower()
    uid  = session.get("user_id") or session.get("uid")
    if not uid:
        return redirect(url_for("auth.login", next=request.full_path))

    # Default tab: workers land on 'accepted', others on 'jobs'
    requested = (request.args.get("tab") or "").strip().lower()
    tab = requested or ("accepted" if role == "worker" else "jobs")

    page = int(request.args.get("page", 1))

    jobs = []
    total = 0
    heading = "My Jobs"

    try:
        if tab == "accepted":
            if role != "worker":
                # Non-workers aren’t allowed to see this tab
                return redirect(url_for("account.me", tab="jobs"))
            heading = "Accepted Jobs"
            rows, total = api.list_accepted_jobs(worker_id=uid, page=page, page_size=20)
            # rows are accepted_jobs with embedded job
            jobs = rows
        elif tab == "jobs":
            heading = "My Jobs"
            # Your existing logic for owned/posted jobs (adjust as you already had)
            rows, total = api.list_jobs_api(
                page=page, page_size=20,
                filters={"customer_id": f"eq.{uid}"},
                order="created_at.desc,id.desc",
                select="id,title,category,location,budget,status,created_at"
            )
            jobs = rows
        elif tab == "settings":
            heading = "Settings"
        else:
            # Fallback
            return redirect(url_for("account.me", tab="jobs"))
    except Exception as e:
        flash(f"Could not load data: {e}", "danger")

    return render_template(
        "profile.html",
        tab=tab,
        heading=heading,
        jobs=jobs,
        total=total or (len(jobs) if jobs else 0),
        page=page,
        role=role,
        user={
            "id": uid,
            "name": session.get("user_name"),
            "email": session.get("user_email"),
            "role": role,
        }
    )

@bp.post("/me/profile")
def update_profile():
    if not require_auth():
        return redirect(url_for("auth.login"))

    name = (request.form.get("name") or "").strip()
    contact = (request.form.get("contact") or "").strip()
    location = (request.form.get("location") or "").strip()

    try:
        # You may not have this yet—see API helper below
        api.update_user_api(session["user_id"], {
            "name": name or None,
            "contact": contact or None,
            "location": location or None
        })
        # refresh session name
        if name: session["user_name"] = name
        flash("Profile updated.", "success")
    except Exception as e:
        flash(f"Could not update profile: {e}", "danger")

    return redirect(url_for("account.me", tab="settings"))

@bp.post("/me/password")
def change_password():
    if not require_auth():
        return redirect(url_for("auth.login"))

    pw = request.form.get("password") or ""
    pw2 = request.form.get("password2") or ""
    if len(pw) < 8:
        flash("Password must be at least 8 characters.", "warning")
        return redirect(url_for("account.me", tab="settings"))
    if pw != pw2:
        flash("Passwords do not match.", "warning")
        return redirect(url_for("account.me", tab="settings"))

    try:
        api.update_user_api(session["user_id"], {
            "password_hash": generate_password_hash(pw)
        })
        flash("Password changed.", "success")
    except Exception as e:
        flash(f"Could not change password: {e}", "danger")

    return redirect(url_for("account.me", tab="settings"))
