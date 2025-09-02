from __future__ import annotations
from urllib.parse import quote
from flask import Blueprint, current_app, render_template, request, redirect, url_for, flash, session
import requests

from . import api
from .common import friendly_datetime, pgrst_base_and_headers

bp = Blueprint("applications", __name__)

def _ok_rows(resp):
    try:
        return resp.status_code == 200 and bool(resp.json())
    except Exception:
        return False

def _decline_other_apps(base, headers, job_id, keep_app_id):
    """Auto-decline all applications on a job except keep_app_id."""
    try:
        requests.patch(
            f"{base}/job_applications?job_id=eq.{job_id}&id=neq.{keep_app_id}",
            headers=headers,
            json={"status": "declined"},
            timeout=6
        )
    except Exception:
        current_app.logger.exception("Auto-decline others failed")

def _job_set_status(base, headers, job_id, status):
    try:
        requests.patch(
            f"{base}/jobs?id=eq.{job_id}",
            headers=headers,
            json={"status": status},
            timeout=6
        )
    except Exception:
        current_app.logger.exception("Set job.status failed")

@bp.post("/jobs/<int:job_id>/apply", endpoint="apply_to_job")
def apply_to_job(job_id: int):
    # Must be logged in (role-agnostic)
    user_id = session.get("user_id")
    if not user_id:
        flash("Please log in to apply.", "warning")
        return redirect(url_for("auth.login", next=request.path))

    # Load + validate job
    try:
        job = api.get_job_api(job_id)
        if not job:
            flash("Job not found.", "danger")
            return redirect(url_for("jobs.list_jobs"))
    except Exception as e:
        current_app.logger.exception("Error fetching job %s: %s", job_id, e)
        flash("Error loading job details.", "danger")
        return redirect(url_for("jobs.list_jobs"))

    # Block self-apply
    if job.get("customer_id") == user_id:
        flash("You cannot apply to your own job.", "warning")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    # Only accept applications for open jobs
    if (job.get("status") or "").lower() != "open":
        flash("This job is not open for applications.", "warning")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    # Prevent duplicate applications (UI safety net + DB-friendly)
    try:
        existing = api.get_applications_for_user(job_id, user_id)  # returns list
        if existing:
            flash("You already applied for this job.", "info")
            return redirect(url_for("jobs.job_detail", job_id=job_id))
    except Exception as e:
        current_app.logger.warning("Could not check existing applications: %s", e)

    # Read + normalize form values
    proposal = (request.form.get("proposal") or "").strip() or None
    bid_raw  = (request.form.get("bid_cents") or "").replace(",", "").replace(" ", "")
    days_raw = (request.form.get("days_to_complete") or "").strip()

    def _int_or_none(s):
        try:
            return int(s) if s not in (None, "",) else None
        except (TypeError, ValueError):
            return None

    bid_cents = _int_or_none(bid_raw)
    days      = _int_or_none(days_raw)

    payload = {
        "job_id": job_id,
        "applicant_id": user_id,      # schema is role-agnostic
        "proposal": proposal,
        "bid_cents": bid_cents,
        "days_to_complete": days,
    }

    base, headers = pgrst_base_and_headers()

    def _post_to(path, *, upsert=False):
        # If you added a UNIQUE(job_id, applicant_id), you can make this idempotent:
        #   POST /job_applications?on_conflict=job_id,applicant_id
        #   Prefer: resolution=merge-duplicates,return=representation
        h = {**headers, "Prefer": "return=representation"}
        url = f"{base}/{path}"
        if upsert:
            h["Prefer"] = "resolution=merge-duplicates,return=representation"
            url = f"{url}?on_conflict=job_id,applicant_id"
        return requests.post(url, headers=h, json=payload, timeout=8)

    # Try create (optionally as upsert if you enabled unique constraint)
    try:
        r = _post_to("job_applications")  # set upsert=True if you added the unique index
    except requests.RequestException:
        current_app.logger.exception("POST /job_applications failed (network)")
        flash("Network error reaching the database API.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    if r.status_code in (200, 201):
        flash("Application submitted!", "success")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    # Error handling
    try:
        body = r.json()
        msg = body.get("message") or body.get("hint") or body
    except Exception:
        msg = r.text or None

    if r.status_code == 409:
        # Conflict most likely due to unique constraint on (job_id, applicant_id)
        flash("You already applied for this job.", "info")
    elif r.status_code in (401, 403):
        flash("Not authorized to apply. (401/403 from PostgREST)", "danger")
    elif r.status_code == 404:
        base_url = base.rstrip("/")
        flash(
            f"PostgREST 404: endpoint not found at {base_url}/job_applications. "
            f"Check table name & exposed schemas. Details: {msg}",
            "danger",
        )
    else:
        flash(f"Could not submit application (HTTP {r.status_code}). Details: {msg}", "danger")

    return redirect(url_for("jobs.job_detail", job_id=job_id))

@bp.get("/jobs/<int:job_id>/apply", endpoint="apply_form")
def apply_form(job_id: int):
    user_id = session.get("user_id")
    if not user_id:
        flash("Please log in to apply.", "warning")
        return redirect(url_for("auth.login", next=request.path))

    # Load job
    try:
        job = api.get_job_api(job_id)
        if not job:
            flash("Job not found.", "danger")
            return redirect(url_for("jobs.list_jobs"))
    except Exception as e:
        flash(f"Error loading job: {e}", "danger")
        return redirect(url_for("jobs.list_jobs"))

    # Block applying to your own job
    if job.get("customer_id") == user_id:
        flash("You can’t apply to your own job.", "warning")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    # Only allow applying when job is open
    if (job.get("status") or "").lower() != "open":
        flash("This job is not open for applications.", "warning")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    # Display helpers
    budget_cents = job.get("budget_cents")
    budget_cents_display = (
        f"G${budget_cents:,}" if isinstance(budget_cents, int) else (budget_cents or "")
    )
    created_at_display = friendly_datetime(job.get("created_at"))

    return render_template(
        "jobs/apply.html",
        job=job,
        budget_cents_display=budget_cents_display,
        created_at_display=created_at_display,
    )

@bp.get("/jobs/<int:job_id>/applications", endpoint="list_applications")
def list_applications(job_id: int):
    # TODO: authorize owner/admin
    base, headers = pgrst_base_and_headers()
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
    # TODO: authorize owner/admin
    base, headers = pgrst_base_and_headers()

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
        return redirect(url_for("applications.list_applications", job_id=job_id))

    if r.status_code in (200, 204):
        flash("Application accepted. Others auto-declined.", "success")
    else:
        msg = None
        try:
            msg = r.json().get("message") or r.json().get("hint")
        except Exception:
            pass
        flash(msg or f"Could not accept application (HTTP {r.status_code}).", "danger")

    return redirect(url_for("applications.list_applications", job_id=job_id))


@bp.post("/jobs/<int:job_id>/applications/<int:app_id>/withdraw", endpoint="withdraw_application")
def withdraw_application(job_id: int, app_id: int):
    user_id = session.get("user_id")
    role = session.get("role")
    if not user_id or role != "worker":
        flash("Please log in as a worker.", "warning")
        return redirect(url_for("auth.login", next=request.path))

    base, headers = pgrst_base_and_headers()
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



#These two endpoints are for when a customer is accepting and rejecting proposals 
@bp.post("/jobs/<int:job_id>/applications/<int:app_id>/offer", endpoint="offer_application")
def offer_application(job_id: int, app_id: int):
    base, headers = pgrst_base_and_headers()

    # A) Read the application first (prove it exists and belongs to this job)
    gr = requests.get(
        f"{base}/job_applications?id=eq.{app_id}&select=id,job_id,status&limit=1",
        headers=headers, timeout=5
    )
    if not gr.ok or not gr.json():
        flash(f"Application id={app_id} not found (SELECT).", "warning")
        return redirect(url_for("account.me", tab="jobs"))

    before = gr.json()[0]
    if str(before["job_id"]) != str(job_id):
        flash(f"Application {app_id} does not belong to job {job_id}.", "warning")
        return redirect(url_for("account.me", tab="jobs"))

    # B) Update the application -> offered
    pr = requests.patch(
        f"{base}/job_applications?id=eq.{app_id}",
        headers={**headers, "Prefer": "return=minimal"},
        json={"status": "offered"},
        timeout=6
    )
    if pr.status_code not in (200, 204):
        try:
            body = pr.json()
        except Exception:
            body = pr.text
        flash(f"Update failed (HTTP {pr.status_code}). {body}", "danger")
        return redirect(url_for("account.me", tab="jobs"))

    # C) Verify the application actually changed
    gr2 = requests.get(
        f"{base}/job_applications?id=eq.{app_id}&select=id,job_id,status&limit=1",
        headers=headers, timeout=5
    )
    if not gr2.ok or not gr2.json() or (gr2.json()[0].get("status") or "").lower() != "offered":
        flash("Application did not change to 'offered' (RLS/constraint?).", "warning")
        return redirect(url_for("account.me", tab="jobs"))

    # D) Now update the JOB status -> offered
    jr = requests.patch(
        f"{base}/jobs?id=eq.{job_id}",
        headers={**headers, "Prefer": "return=representation"},
        json={"status": "offered"},
        timeout=5
    )

    if jr.status_code == 200 and jr.json():
        flash("Offer sent and job marked as offered.", "success")
    elif jr.status_code in (200, 204):
        # representation might be empty due to RLS; do a quick check
        jcheck = requests.get(
            f"{base}/jobs?id=eq.{job_id}&select=id,status&limit=1",
            headers=headers, timeout=5
        )
        if jcheck.ok and jcheck.json() and (jcheck.json()[0].get("status") or "").lower() == "offered":
            flash("Offer sent and job marked as offered.", "success")
        else:
            flash("Application offered, but job status didn’t change (RLS/constraint on jobs?).", "warning")
    else:
        try:
            err = jr.json()
        except Exception:
            err = jr.text
        flash(f"Application offered, but job update failed (HTTP {jr.status_code}). {err}", "warning")

    return redirect(url_for("account.me", tab="jobs"))

@bp.post("/jobs/<int:job_id>/applications/<int:app_id>/reject", endpoint="reject_application_by_customer")
def reject_application_by_customer(job_id: int, app_id: int):
    """
    Owner-only: reject a proposal. If the rejected app was the current 'offered'
    and no other apps are 'offered', mark the job back to 'open'.
    """
    uid = session.get("user_id")
    if not uid:
        flash("Please log in.", "warning")
        return redirect(url_for("auth.login", next=request.path))

    base, headers = pgrst_base_and_headers()

    # 1) Read the application (ensure it exists and belongs to the job)
    r0 = requests.get(
        f"{base}/job_applications?id=eq.{app_id}&select=id,job_id,status&limit=1",
        headers=headers, timeout=6
    )
    if not r0.ok or not r0.json():
        flash("Application not found.", "warning")
        return redirect(url_for("account.me", tab="jobs"))

    app = r0.json()[0]
    if str(app.get("job_id")) != str(job_id):
        flash("This application does not belong to the selected job.", "warning")
        return redirect(url_for("account.me", tab="jobs"))

    # 2) Verify current user owns the job
    rj = requests.get(
        f"{base}/jobs?id=eq.{job_id}&select=id,poster_id,status&limit=1",
        headers=headers, timeout=6
    )
    if not rj.ok or not rj.json():
        flash("Job not found.", "warning")
        return redirect(url_for("account.me", tab="jobs"))

    job = rj.json()[0]
    if str(job.get("poster_id")) != str(uid):
        flash("Only the job owner can reject proposals.", "warning")
        return redirect(url_for("account.me", tab="jobs"))

    was_offered = ((app.get("status") or "").lower() == "offered")

    # 3) Decline the application (by PK only)
    r1 = requests.patch(
        f"{base}/job_applications?id=eq.{app_id}",
        headers={**headers, "Prefer": "return=minimal"},
        json={"status": "declined"},
        timeout=8
    )
    if r1.status_code not in (200, 204):
        try:
            err = r1.json()
        except Exception:
            err = r1.text
        flash(f"Could not decline (HTTP {r1.status_code}). {err}", "danger")
        return redirect(url_for("account.me", tab="jobs"))

    # 4) If we just declined the offered app, and there are no other offers, set job back to open
    if was_offered:
        r2 = requests.get(
            f"{base}/job_applications?job_id=eq.{job_id}&status=eq.offered&select=id&limit=1",
            headers=headers, timeout=6
        )
        others_offered = (r2.ok and bool(r2.json()))
        if not others_offered:
            r3 = requests.patch(
                f"{base}/jobs?id=eq.{job_id}",
                headers={**headers, "Prefer": "return=minimal"},
                json={"status": "open"},
                timeout=8
            )
            if r3.status_code not in (200, 204):
                try:
                    err = r3.json()
                except Exception:
                    err = r3.text
                flash(f"Declined, but job status update failed (HTTP {r3.status_code}). {err}", "warning")
                return redirect(url_for("account.me", tab="jobs"))

    flash("Proposal declined.", "info")
    return redirect(url_for("account.me", tab="jobs"))




#These two endpoints are for when a worker is accepting and rejecting offered jobs
@bp.post("/jobs/<int:job_id>/applications/<int:app_id>/accept-offer", endpoint="worker_accept_offer")
def worker_accept_offer(job_id: int, app_id: int):
    """
    Accept an offer (no role checks):
      - require app.status='offered' and job.status in ('offered','open')
      - insert into accepted_jobs FIRST
      - set application -> 'accepted'
      - set job -> 'assigned'
      - decline all other applications for this job
    """
    uid = session.get("user_id")
    if not uid:
        flash("Please log in.", "warning")
        return redirect(url_for("auth.login", next=request.path))

    base, headers = pgrst_base_and_headers()

    # 1) Read the application and validate ownership + linkage to job
    ra = requests.get(
        f"{base}/job_applications"
        f"?id=eq.{app_id}"
        f"&select=id,job_id,applicant_id,status"
        f"&limit=1",
        headers=headers, timeout=6
    )
    if not ra.ok or not ra.json():
        flash("Application not found.", "warning")
        return redirect(url_for("account.me", tab="applications"))

    app = ra.json()[0]

    if str(app.get("job_id")) != str(job_id):
        flash("Application does not belong to this job.", "warning")
        return redirect(url_for("account.me", tab="applications"))

    # If your schema still uses worker_id instead of applicant_id, use this check instead:
    # if str(app.get("worker_id")) != str(uid): ...

    if str(app.get("applicant_id")) != str(uid):
        flash("You can only accept offers made to you.", "warning")
        return redirect(url_for("account.me", tab="applications"))

    if (app.get("status") or "").lower() != "offered":
        flash("This application is not currently offered.", "warning")
        return redirect(url_for("account.me", tab="applications"))

    # 2) Read the job and validate state
    rj = requests.get(
        f"{base}/jobs?id=eq.{job_id}&select=id,status&limit=1",
        headers=headers, timeout=6
    )
    if not rj.ok or not rj.json():
        flash("Job not found.", "warning")
        return redirect(url_for("account.me", tab="applications"))

    job = rj.json()[0]
    job_status = (job.get("status") or "").lower()
    if job_status not in ("offered", "open"):
        flash(f"Job is not in an offerable state (current: {job.get('status')}).", "warning")
        return redirect(url_for("account.me", tab="applications"))

    # 3) Insert into accepted_jobs FIRST (idempotent-friendly)
    ins_payload = {
        "job_id": job_id,
        "application_id": app_id,  # ✅ the application PK
        "worker_id": uid,          # ✅ the logged-in user
    }
    ins = requests.post(
        f"{base}/accepted_jobs",
        headers={**headers, "Prefer": "return=representation"},
        json=ins_payload,
        timeout=6
    )


    if ins.status_code not in (200, 201, 409):  # 409 = already recorded (ok)
        try:
            err = ins.json()
        except Exception:
            err = ins.text or "<no error body>"
        flash(f"Could not record acceptance (PostgREST {ins.status_code}). {err}", "danger")
        return redirect(url_for("account.me", tab="applications"))


    # 4) Mark this application as 'accepted'
    ua = requests.patch(
        f"{base}/job_applications?id=eq.{app_id}",
        headers={**headers, "Prefer": "return=minimal"},
        json={"status": "accepted"},
        timeout=6
    )
    if ua.status_code not in (200, 204):
        try:
            err = ua.json()
        except Exception:
            err = ua.text
        flash(f"Accepted, but failed to update application (HTTP {ua.status_code}). {err}", "warning")
        return redirect(url_for("account.me", tab="applications"))

    # 5) Update job status to 'assigned' (or 'accepted' if that's your state)
    uj = requests.patch(
        f"{base}/jobs?id=eq.{job_id}",
        headers={**headers, "Prefer": "return=minimal"},
        json={"status": "accepted"},
        timeout=6
    )
    if uj.status_code not in (200, 204):
        try:
            err = uj.json()
        except Exception:
            err = uj.text
        flash(f"Accepted, but job status update failed (HTTP {uj.status_code}). {err}", "warning")

    # 6) Decline all other applications for this job (best effort)
    try:
        requests.patch(
            f"{base}/job_applications?job_id=eq.{job_id}&id=neq.{app_id}",
            headers=headers,
            json={"status": "declined"},
            timeout=6
        )
    except Exception:
        pass

    flash("Offer accepted. Job assigned and recorded.", "success")
    return redirect(url_for("account.me", tab="applications"))


@bp.post("/jobs/<int:job_id>/applications/<int:app_id>/reject-offer", endpoint="worker_reject_offer")
def worker_reject_offer(job_id: int, app_id: int):
    """Reject an offer. Only the applicant who owns the application can do this.
       If no other offers remain, job may go back to open.
    """
    uid = session.get("user_id")
    if not uid:
        flash("Please log in to reject offers.", "warning")
        return redirect(url_for("auth.login", next=request.path))

    base, headers = pgrst_base_and_headers()

    # 1) Verify this application belongs to the current user
    ra = requests.get(
        f"{base}/job_applications?id=eq.{app_id}&job_id=eq.{job_id}&select=id,applicant_id,status&limit=1",
        headers=headers, timeout=6
    )
    if not ra.ok or not ra.json():
        flash("Application not found.", "warning")
        return redirect(url_for("account.me", tab="applications"))

    app = ra.json()[0]
    if str(app.get("applicant_id")) != str(uid):
        flash("You can only reject offers made to you.", "warning")
        return redirect(url_for("account.me", tab="applications"))

    # 2) Decline the application
    try:
        r = requests.patch(
            f"{base}/job_applications?id=eq.{app_id}",
            headers=headers,
            json={"status": "declined"},
            timeout=6
        )
    except requests.RequestException:
        current_app.logger.exception("PATCH reject-offer failed")
        flash("Network error while rejecting offer.", "danger")
        return redirect(url_for("account.me", tab="applications"))

    if r.status_code in (200, 204):
        # 3) If job was offered, and no other offers remain, reopen job
        try:
            still_offered = requests.get(
                f"{base}/job_applications?job_id=eq.{job_id}&status=eq.offered&select=id&limit=1",
                headers=headers, timeout=6
            )
            if still_offered.ok and not still_offered.json():
                _job_set_status(base, headers, job_id, "open")
        except Exception:
            pass
        flash("Offer rejected.", "info")
    else:
        try:
            err = r.json()
        except Exception:
            err = r.text
        flash(f"Could not reject offer (HTTP {r.status_code}). {err}", "danger")

    return redirect(url_for("account.me", tab="applications"))
