
from __future__ import annotations
from collections import defaultdict

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from urllib.parse import quote, quote_plus
from datetime import datetime
from typing import Optional

import requests

from microjobs.common import pgrst_base_and_headers
from microjobs.routes import require_auth
from . import api
from werkzeug.security import generate_password_hash, check_password_hash

bp = Blueprint("account", __name__)

def _total_from(resp, fallback_len: int) -> int:
    cr = resp.headers.get("Content-Range")
    if cr and "/" in cr:
        try:
            return int(cr.split("/")[-1])
        except Exception:
            return fallback_len
    return fallback_len

def current_db_user_id():
    # Prefer a value we've already saved explicitly
    val = session.get("db_user_id") or session.get("user_id") or session.get("uid")

    # If it's already an int, great
    if isinstance(val, int):
        return val

    # If it's a numeric string like "42", coerce
    if isinstance(val, str) and val.isdigit():
        return int(val)

    # Otherwise we have an auth UID or email; map it to the DB id once and cache it
    base, headers = pgrst_base_and_headers()

    # Try by auth UID if you store it on users (e.g., users.auth_uid)
    auth_uid = session.get("uid")
    if auth_uid:
        r = requests.get(
            f"{base}/users?auth_uid=eq.{quote(auth_uid)}&select=id&limit=1",
            headers=headers, timeout=5
        )
        if r.ok and r.json():
            db_id = r.json()[0]["id"]
            session["db_user_id"] = db_id
            return db_id

    # Fallback: try by email
    email = session.get("user_email")
    if email:
        r = requests.get(
            f"{base}/users?email=eq.{quote(email)}&select=id&limit=1",
            headers=headers, timeout=5
        )
        if r.ok and r.json():
            db_id = r.json()[0]["id"]
            session["db_user_id"] = db_id
            return db_id

    # If all else fails, treat as not logged-in properly
    raise RuntimeError("Could not resolve DB user id from session")


@bp.route("/me")
def me():
    role = (session.get("role") or "").lower()
    uid = current_db_user_id() 
    if not uid:
        return redirect(url_for("auth.login", next=request.full_path))

    # Default tab: workers → 'accepted', everyone else → 'jobs'
    requested = (request.args.get("tab") or "").strip().lower()
    tab = requested or ("accepted" if role == "worker" else "jobs")

    page = int(request.args.get("page", 1))
    page_size = 20
    offset = (page - 1) * page_size

    base, headers = pgrst_base_and_headers()
    jobs, total = [], 0

    # ------------------------
    # CUSTOMER: My Jobs (+ embedded applications)
    # ------------------------
    if tab == "jobs":
        if role != "customer":
            # Workers don't have "posted jobs"; send them to their default
            return redirect(url_for("account.me", tab=("accepted" if role == "worker" else "settings")))

        heading = "My Jobs (with Applications)"
        h = {**headers, "Prefer": "count=exact"}

        try:
            # Try embedding applications + worker info (requires FKs)
            r = requests.get(
                f"{base}/jobs"
                f"?customer_id=eq.{uid}"
                f"&select=id,title,category,location,budget,status,created_at,"
                f"applications:job_applications(*,worker:users(name))"
                f"&order=created_at.desc,id.desc"
                f"&limit={page_size}&offset={offset}",
                headers=h, timeout=8
            )
            if r.ok:
                jobs = r.json()
                total = _total_from(r, len(jobs))
            else:
                # Fallback: fetch jobs then apps separately and stitch by job_id
                rj = requests.get(
                    f"{base}/jobs"
                    f"?customer_id=eq.{uid}"
                    f"&select=id,title,category,location,budget,status,created_at"
                    f"&order=created_at.desc,id.desc"
                    f"&limit={page_size}&offset={offset}",
                    headers=h, timeout=8
                )
                if rj.ok:
                    jobs = rj.json()
                    total = _total_from(rj, len(jobs))
                    job_ids = [str(j["id"]) for j in jobs if "id" in j]
                    if job_ids:
                        ra = requests.get(
                            f"{base}/job_applications"
                            f"?job_id=in.({','.join(job_ids)})"
                            f"&select=*,worker:users(name,contact)"
                            f"&order=created_at.desc",
                            headers=headers, timeout=8
                        )
                        apps_by_job = defaultdict(list)
                        if ra.ok:
                            for a in ra.json():
                                apps_by_job[a["job_id"]].append(a)
                        for j in jobs:
                            j["applications"] = apps_by_job.get(j["id"], [])
        except Exception as e:
            flash(f"Could not load your jobs/applications: {e}", "danger")

        return render_template(
            "profile.html",
            tab=tab, heading=heading,
            jobs=jobs, total=total or (len(jobs) if jobs else 0),
            page=page, role=role,
            user={
                "id": uid,
                "name": session.get("user_name"),
                "email": session.get("user_email"),
                "role": role,
            },
        )

    # ------------------------
    # WORKER: Applications tab (your applications + embedded job)
    # ------------------------
    if tab == "applications":
        if role != "worker":
            return redirect(url_for("account.me", tab="jobs"))

        heading = "My Applications"
        h = {**headers, "Prefer": "count=exact"}

        try:
            r = requests.get(
                f"{base}/job_applications"
                f"?worker_id=eq.{uid}"
                f"&select=*,job:jobs(*)"
                f"&order=created_at.desc"
                f"&limit={page_size}&offset={offset}",
                headers=h, timeout=8
            )
            if r.ok:
                jobs = r.json()
                total = _total_from(r, len(jobs))
        except Exception as e:
            flash(f"Could not load your applications: {e}", "danger")

        return render_template(
            "profile.html",
            tab=tab, heading=heading,
            jobs=jobs, total=total or (len(jobs) if jobs else 0),
            page=page, role=role,
            user={
                "id": uid,
                "name": session.get("user_name"),
                "email": session.get("user_email"),
                "role": role,
            },
        )

    # ------------------------
    # WORKER: Accepted tab (assigned jobs)
    # ------------------------
    if tab == "accepted":
        if role != "worker":
            return redirect(url_for("account.me", tab="jobs"))

        heading = "Accepted Jobs"
        h = {**headers, "Prefer": "count=exact"}

        try:
            # Preferred: accepted_jobs join
            r = requests.get(
                f"{base}/accepted_jobs"
                f"?worker_id=eq.{uid}"
                f"&select=accepted_at,job:jobs(*)"
                f"&order=accepted_at.desc"
                f"&limit={page_size}&offset={offset}",
                headers=h, timeout=8
            )
            if r.ok and r.json():
                jobs = r.json()
                total = _total_from(r, len(jobs))
            else:
                # Fallback: applications where status=accepted
                r2 = requests.get(
                    f"{base}/job_applications"
                    f"?worker_id=eq.{uid}&status=eq.accepted"
                    f"&select=created_at,job:jobs(*)"
                    f"&order=created_at.desc"
                    f"&limit={page_size}&offset={offset}",
                    headers=h, timeout=8
                )
                if r2.ok:
                    jobs = [{"accepted_at": row.get("created_at"), "job": row.get("job")} for row in r2.json()]
                    total = _total_from(r2, len(jobs))
        except Exception as e:
            flash(f"Could not load accepted jobs: {e}", "danger")

        return render_template(
            "profile.html",
            tab=tab, heading=heading,
            jobs=jobs, total=total or (len(jobs) if jobs else 0),
            page=page, role=role,
            user={
                "id": uid,
                "name": session.get("user_name"),
                "email": session.get("user_email"),
                "role": role,
            },
        )

    # ------------------------
    # SETTINGS (or unknown tab)
    # ------------------------
    if tab == "settings":
        heading = "Settings"
        return render_template(
            "profile.html",
            tab=tab, heading=heading,
            jobs=[], total=0, page=page, role=role,
            user={
                "id": uid,
                "name": session.get("user_name"),
                "email": session.get("user_email"),
                "role": role,
            },
        )

    # Fallback to role default
    return redirect(url_for("account.me", tab=("accepted" if role == "worker" else "jobs")))





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
