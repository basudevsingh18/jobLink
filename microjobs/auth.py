# microjobs/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, session, flash

bp = Blueprint("auth", __name__, url_prefix="/auth")

# In-memory store (replace with DB later)
USERS = []
# In-memory store (replace with DB later)
USERS = [
    {
        "id": 1,
        "name": "Alice Customer",
        "email": "customer@test.com",
        "role": "customer",
        "password": "1234",
    },
    {
        "id": 2,
        "name": "Bob Worker",
        "email": "worker@test.com",
        "role": "worker",
        "password": "1234",
    },
    {
        "id": 3,
        "name": "Admin Guy",
        "email": "admin@test.com",
        "role": "admin",
        "password": "1234",
    },
]
NEXT_USER_ID = 4

@bp.route("/register", methods=["GET", "POST"])
def register():
    global NEXT_USER_ID
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        role = request.form.get("role", "").strip()  # 'customer' or 'worker'
        password = request.form.get("password", "").strip()

        if not (name and email and password and role):
            flash("Please fill all fields", "warning")
            return render_template("register.html")

        # check if email exists
        if any(u["email"] == email for u in USERS):
            flash("Email already registered", "danger")
            return render_template("register.html")

        user = {
            "id": NEXT_USER_ID,
            "name": name,
            "email": email,
            "role": role,
            "password": password,  # NOTE: plain text (hash later)
        }
        USERS.append(user)
        NEXT_USER_ID += 1

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "").strip()

        user = next((u for u in USERS if u["email"] == email and u["password"] == password), None)
        if not user:
            flash("Invalid credentials", "danger")
            return render_template("login.html")

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        session["role"] = user["role"]
        flash(f"Welcome back, {user['name']}!", "success")
        return redirect(url_for("jobs.list_jobs"))

    return render_template("login.html")

@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("jobs.list_jobs"))
