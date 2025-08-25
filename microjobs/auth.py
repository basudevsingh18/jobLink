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

bp = Blueprint("auth", __name__, url_prefix="/auth")


# -----------------------------
# Helpers
# -----------------------------
def _f(field: str) -> str:
    """Read + trim a form field."""
    return (request.form.get(field) or "").strip()

def _hash_password(pw: str) -> str:
    """Dev-only password hashing (SHA-256)."""
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


# -----------------------------
# Routes
# -----------------------------
@bp.route("/register", methods=["GET", "POST"])
def register():
    """
    Dev registration:
    - Validates presence + role.
    - Checks duplicate email in DB via PostgREST.
    - Stores hashed password in users.password_hash.
    """
    if request.method == "POST":
        name = _f("name")
        email = _f("email").lower()
        role = _f("role")
        password = _f("password")

        # Minimal validation
        if not all([name, email, role, password]):
            flash("Please fill all fields.", "warning")
            return render_template("register.html")

        if role not in ("customer", "worker", "admin"):
            flash("Invalid role selected.", "warning")
            return render_template("register.html")

        # Duplicate email check (DB)
        try:
            existing = api.get_user_by_email(email)
        except Exception as e:
            flash(f"Could not validate email: {e}", "danger")
            return render_template("register.html")

        if existing:
            flash("Email already registered.", "danger")
            return render_template("register.html")

        # Create user in DB
        try:
            user = api.create_user({
                "name": name,
                "email": email,
                "role": role,
                "password_hash": _hash_password(password),
            })
        except Exception as e:
            flash(f"Failed to create account: {e}", "danger")
            return render_template("register.html")

        if not user or "id" not in user:
            flash("Account creation did not return a user.", "danger")
            return render_template("register.html")

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("auth.login"))

    # GET
    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Dev login:
    - Fetch user by email from DB via PostgREST.
    - Compare SHA-256(password) with users.password_hash.
    - Sets session with basic identity (no JWT yet).
    """
    if request.method == "POST":
        email = _f("email").lower()
        password = _f("password")

        try:
            user = api.get_user_by_email(email)
        except Exception as e:
            flash(f"Login error: {e}", "danger")
            return render_template("login.html")

        if not user:
            flash("Invalid credentials.", "danger")
            return render_template("login.html")

        expected = user.get("password_hash") or ""
        if _hash_password(password) != expected:
            flash("Invalid credentials.", "danger")
            return render_template("login.html")

        # Set session keys used across the app
        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        session["user_email"] = user["email"]
        session["role"] = user["role"]
        session["jwt"] = None  # TODO: when /rpc/login is added, store token here

        flash(f"Welcome back, {user['name']}!", "success")
        return redirect(url_for("jobs.list_jobs"))

    # GET
    return render_template("login.html")


@bp.route("/logout")
def logout():
    """Clear session and return to job list."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("jobs.list_jobs"))
