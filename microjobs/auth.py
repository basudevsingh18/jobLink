# microjobs/auth.py
"""
Ultra-simple auth:
- Register: name, email, password -> creates user (role defaults to 'customer')
- Login: email + password
- Logout: clears session

Templates expected:
- templates/register.html  (fields: name, email, password)
- templates/login.html     (fields: email, password)
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from . import api  # PostgREST helper (microjobs/api.py)

bp = Blueprint("auth", __name__, url_prefix="/auth")

# -----------------------------
# Helpers
# -----------------------------
def _f(field: str) -> str:
    return (request.form.get(field) or "").strip()

@bp.before_app_request
def _load_session_user():
    """Make a tiny current_user available to templates (optional but handy)."""
    uid = session.get("user_id") or session.get("uid")
    if uid:
        g.current_user = {
            "id": uid,
            "name": session.get("user_name"),
            "email": session.get("user_email"),
            "role": session.get("role"),
        }
    else:
        g.current_user = None

@bp.app_context_processor
def _inject_user():
    return {
        "current_user": getattr(g, "current_user", None),
        "is_authenticated": bool(getattr(g, "current_user", None)),
    }

# -----------------------------
# Routes
# -----------------------------
@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    name = _f("name")
    email = _f("email").lower()
    password = _f("password")

    if not all([name, email, password]):
        flash("Please fill in name, email, and password.", "warning")
        return render_template("register.html")

    # Check duplicate email
    if api.get_user_by_email(email):
        flash("That email is already registered.", "danger")
        return render_template("register.html")

    # Create user (role defaulted to 'customer', status 'active')
    user = api.create_user({
        "name": name,
        "email": email,
        "password_hash": generate_password_hash(password),  # pbkdf2:sha256
        "role": "customer",
        "status": "active",
    })

    flash("Account created! Please sign in.", "success")
    return redirect(url_for("auth.login"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = _f("email").lower()
    password = _f("password")

    if not all([email, password]):
        flash("Enter your email and password.", "warning")
        return render_template("login.html")

    user = api.get_user_by_email(email)
    if not user or not check_password_hash(user.get("password_hash") or "", password):
        flash("Invalid email or password.", "danger")
        return render_template("login.html")

    # Minimal session
    session.clear()
    session["user_id"] = user["id"]   # canonical
    session["uid"] = user["id"]       # legacy compat (if other code checks this)
    session["user_name"] = user.get("name")
    session["user_email"] = user.get("email")
    session["role"] = user.get("role") or "customer"

    return redirect(url_for("jobs.list_jobs"))


@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("jobs.list_jobs"))

@bp.route("/forgot-password")
def forgot_password():
    flash("Password reset is not available in the basic mode.", "info")
    return redirect(url_for("auth.login"))

