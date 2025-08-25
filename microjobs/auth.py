# microjobs/auth.py
"""
Auth blueprint backed by PostgREST (DB), dev-safe:

- Registration inserts into the DB (via PostgREST).
- Login fetches user by email from the DB and verifies a simple SHA-256 hash.
- Session keys set: user_id, user_name, user_email, role, jwt (None for now).

TODO (production):
- Replace SHA-256 with proper hashing (e.g., bcrypt) or move hashing into DB via pgcrypto.
- Implement /rpc/login in Postgres that validates password and returns a JWT.
- Switch this blueprint to call api.login_rpc(), then set session['jwt'] from token.
- Enforce RLS in DB and remove anon write privileges.
"""

from datetime import datetime, timedelta
import token
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import hashlib
from . import api  # PostgREST helper module (microjobs/api.py)
from werkzeug.security import generate_password_hash, check_password_hash
from microjobs.security import make_email_token, hash_token, read_email_token
from microjobs.audit import log_event
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

bp = Blueprint("auth", __name__, url_prefix="/auth")
limiter = Limiter(key_func=get_remote_address)


# -----------------------------
# Helpers
# -----------------------------
def _f(field: str) -> str:
    """Read + trim a form field."""
    return (request.form.get(field) or "").strip()


def _hash_password(pw: str) -> str:
    return generate_password_hash(pw)


# -----------------------------
# Routes
# -----------------------------
@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").lower().strip()
    role = request.form.get("role", "").strip()
    pw = request.form.get("password", "")

    # Minimal validation + allow only customer/worker self-serve
    if not all([name, email, role, pw]) or role not in ("customer", "worker"):
        flash("Please fill all fields and choose a valid role.", "warning")
        return render_template("register.html")

    if api.get_user_by_email(email):
        flash("That email is already registered.", "danger")
        return render_template("register.html")

    password_hash = generate_password_hash(pw)

    # Create pending user
    token_raw = make_email_token(email)
    token_h = hash_token(token_raw)
    expires = datetime.utcnow() + timedelta(hours=24)

    user = api.create_user(
        {
            "name": name,
            "email": email,
            "role": role,
            "password_hash": password_hash,
            "status": "pending",
            "verification_token": token_h,
            "verification_expires": expires.isoformat(),
            "terms_version": "v1.0",
            "terms_accepted_at": datetime.utcnow().isoformat(),
        }
    )

    # Send email (use your mailer/adapter)
    verify_url = url_for("auth.verify_email", token=token, _external=True)

    api.send_email(
        to=email,
        subject="Verify your JobLink account",
        html=render_template("emails/verify.html", name=name, verify_url=verify_url)
)

    log_event(user["id"], "REGISTERED", {"role": role})
    log_event(user["id"], "EMAIL_SENT", {"type": "verification"})

    flash("Check your email to verify your account (link valid for 24 hours).", "info")
    return redirect(url_for("auth.login"))


@bp.route("/verify")
@limiter.limit("20 per hour")
def verify_email():
    token = request.args.get("token", "")
    try:
        email = read_email_token(token, max_age=60 * 60 * 24)
    except Exception:
        flash("Invalid or expired verification link.", "danger")
        return redirect(url_for("auth.login"))

    user = api.get_user_by_email(email)
    if not user:
        flash("Account not found.", "danger")
        return redirect(url_for("auth.login"))

    # constant-time compare (hash)
    if user.get("verification_token") != hash_token(token):
        flash("Invalid verification token.", "danger")
        return redirect(url_for("auth.login"))

    if user.get("status") == "active":
        flash("Your email is already verified.", "info")
        return redirect(url_for("auth.login"))

    if user.get("verification_expires") and datetime.utcnow() > datetime.fromisoformat(
        user["verification_expires"]
    ):
        flash("This link has expired. Request a new verification email.", "warning")
        return redirect(url_for("auth.resend_verification"))

    # Activate
    api.update_user(
        user["id"],
        {
            "status": "active",
            "email_verified_at": datetime.utcnow().isoformat(),
            "verification_token": None,
            "verification_expires": None,
        },
    )
    log_event(user["id"], "EMAIL_VERIFIED", {})
    flash("Email verified! You can now sign in.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/resend-verification", methods=["POST"])
@limiter.limit("3 per hour")
def resend_verification():
    email = request.form.get("email", "").lower().strip()
    user = api.get_user_by_email(email)
    if not user:
        flash("If that email exists, a message will be sent.", "info")
        return redirect(url_for("auth.login"))

    if user.get("status") == "active":
        flash("This account is already verified.", "info")
        return redirect(url_for("auth.login"))

    # reissue token
    token_raw = make_email_token(email)
    token_h = hash_token(token_raw)
    expires = datetime.utcnow() + timedelta(hours=24)

    api.update_user(
        user["id"],
        {"verification_token": token_h, "verification_expires": expires.isoformat()},
    )
    verify_url = url_for("auth.verify_email", token=token_raw, _external=True)
    api.send_email(
        to=email,
        subject="Verify your JobLink account",
        html=render_template(
            "emails/verify.html", name=user["name"], verify_url=verify_url
        ),
    )
    log_event(user["id"], "EMAIL_SENT", {"type": "verification_resend"})
    flash("If your account is pending, a new verification email was sent.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/logout")
def logout():
    """Clear session and return to job list."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("jobs.list_jobs"))


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").lower().strip()
    pw = request.form.get("password", "")
    ip = request.remote_addr
    ua = request.headers.get("User-Agent", "")

    user = api.get_user_by_email(email)
    if not user:
        flash("Invalid credentials.", "danger")
        return render_template("login.html")

    # Check lockout
    if user.get("lockout_until"):
        from datetime import datetime

        if datetime.utcnow() < datetime.fromisoformat(user["lockout_until"]):
            flash(
                "Account temporarily locked due to multiple failed attempts.", "warning"
            )
            return render_template("login.html")

    # Verify status
    if user.get("status") != "active":
        flash("Please verify your email to continue.", "warning")
        return render_template("login.html")

    if not api.verify_password(user, pw):
        # increment + optional lock
        failed = user.get("failed_attempts", 0) + 1
        lock_until = None
        if failed >= 5:
            from datetime import timedelta

            lock_until = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
            log_event(user["id"], "LOCKED", {"reason": "too_many_failures"})
        api.update_user(
            user["id"], {"failed_attempts": failed, "lockout_until": lock_until}
        )
        log_event(user["id"], "LOGIN_FAILED", {"ip": ip, "ua": ua})
        flash("Invalid credentials.", "danger")
        return render_template("login.html")

    # success
    api.update_user(
        user["id"],
        {
            "failed_attempts": 0,
            "lockout_until": None,
            "last_login_at": datetime.utcnow().isoformat(),
            "last_login_ip": ip,
        },
    )
    log_event(user["id"], "LOGIN_SUCCESS", {"ip": ip, "ua": ua})
    # set session etc...
    session["uid"] = user["id"]
    session["role"] = user["role"]
    return redirect(url_for("jobs.list_jobs"))


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").lower().strip()
        user = api.get_user_by_email(email)
        if user:
            token = make_email_token(email)
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            api.send_email(
                to=email,
                subject="Reset your JobLink password",
                html=render_template("emails/reset_password.html", reset_url=reset_url),
            )
            flash("Password reset link sent to your email.", "info")
        else:
            flash("If that email exists, a reset link was sent.", "info")
        return redirect(url_for("auth.login"))
    return render_template("forgot_password.html")


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = read_email_token(token, max_age=3600)  # 1 hour validity
    except Exception:
        flash("Invalid or expired reset link.", "danger")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        pw = request.form.get("password")
        if not pw or len(pw) < 8:
            flash("Password must be at least 8 characters.", "warning")
            return render_template("reset_password.html")
        api.update_user_password(email, pw)
        flash("Password updated! You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("reset_password.html")
