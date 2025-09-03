# app.py
import os
from flask import Flask
from microjobs.applications import bp as applications_bp
from microjobs.routes import bp as jobs_bp
from microjobs.auth import bp as auth_bp
from microjobs.accounts import bp as account_bp
from microjobs.pages import bp as pages_bp
from werkzeug.middleware.proxy_fix import ProxyFix  # optional but handy when tunneling

def create_app():
    app = Flask(__name__)

    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "59wUd2XmXGU2H4wzbjKaY1vUqxyCQbxExFU5sBnLbe9lMx9VIH"))

    # Register blueprints
    app.register_blueprint(jobs_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(pages_bp)
    app.register_blueprint(applications_bp)

    return app

if __name__ == "__main__":
    app = create_app()  # <-- instantiate your app
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    app.run(host=host, port=port, debug=True)
