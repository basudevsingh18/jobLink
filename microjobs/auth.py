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

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import hashlib
from . import api  # PostgREST helper module (microjobs/api.py)
from werkzeug.security import generate_password_hash, check_password_hash

bp = Blueprint("auth", __name__, url_prefix="/auth")


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
def register():
    if request.method == "POST":
        name = _f("name")
        email = (_f("email") or "").lower().strip()
        role = _f("role")
        password = _f("password")

        if not all([name, email, role, password]):
            flash("Please fill all fields.", "warning")
            return render_template("register.html")

        if role not in ("customer", "worker", "admin"):
            flash("Invalid role selected.", "warning")
            return render_template("register.html")

        # Optional: minimal email format check
        if "@" not in email or "." not in email.split("@")[-1]:
            flash("Please enter a valid email address.", "warning")
            return render_template("register.html")

        try:
            existing = api.get_user_by_email(email)
        except Exception as e:
            flash(f"Could not validate email: {e}", "danger")
            return render_template("register.html")

        if existing:
            flash("Email already registered.", "danger")
            return render_template("register.html")

        try:
            created = api.create_user(
                {
                    "name": name,
                    "email": email,
                    "role": role,
                    "password_hash": _hash_password(password),
                }
            )
        except Exception as e:
            # This is where your original error bubbles up; now it’ll include status/text
            flash(f"Failed to create account: {e}", "danger")
            return render_template("register.html")

        # Handle both shapes
        new_id = (created or {}).get("id") if isinstance(created, dict) else None
        if not new_id:
            # If you used Option A, this shouldn't happen. If Option B, it's okay.
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("auth.login"))

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("auth.login"))

    # GET
    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Dev login:
    - Fetch user by email from DB via PostgREST.
    - Verify plaintext password with werkzeug.check_password_hash.
    - Sets session with basic identity (no JWT yet).
    """
    if request.method == "POST":
        email = (_f("email") or "").strip().lower()
        password = _f("password") or ""

        try:
            user = api.get_user_by_email(email)
        except Exception as e:
            flash(f"Login error: {e}", "danger")
            return render_template("login.html")

        if not user:
            flash("Invalid credentials.", "danger")
            return render_template("login.html")

        stored = user.get("password_hash") or ""
        if not check_password_hash(stored, password):
            flash("Invalid credentials.", "danger")
            return render_template("login.html")

        # Clear old session and set new identity
        session.clear()
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        session["user_email"] = user["email"]
        session["role"] = user["role"]
        session["jwt"] = None  # TODO: replace with real token later

        flash(f"Welcome back, {user['name']}!", "success")
        return redirect(url_for("jobs.list_jobs"))

    return render_template("login.html")

@bp.route("/logout")
def logout():
    """Clear session and return to job list."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("jobs.list_jobs"))
