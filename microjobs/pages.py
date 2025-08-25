# microjobs/pages.py
from flask import Blueprint, render_template

bp = Blueprint("pages", __name__)

@bp.route("/terms")
def terms():
    # renders templates/terms.html
    return render_template("terms.html")
