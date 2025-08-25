
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
    if not require_auth():
        return redirect(url_for("auth.login"))

    tab = request.args.get("tab", "overview")
    uid = session["user_id"]

    # Basic user info (from session; fetch fresh if you prefer)
    user = {
        "id": uid,
        "name": session.get("user_name"),
        "email": session.get("user_email"),
        "role": session.get("role"),
    }

    jobs, total = [], 0
    if tab in ("overview", "jobs"):
        try:
            jobs, total = api.list_jobs_api(
                select="id,title,category,location,budget,status,created_at,customer_id",
                order="created_at.desc,id.desc",
                page=int(request.args.get("page", 1)),
                page_size=20,
                filters={"customer_id": f"eq.{uid}"}
            )
        except Exception as e:
            flash(f"Could not load your jobs: {e}", "danger")

    return render_template("profile.html",
                           user=user, tab=tab,
                           jobs=jobs, total=total or len(jobs),
                           page=int(request.args.get("page", 1)))

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
