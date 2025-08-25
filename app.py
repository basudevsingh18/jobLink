# app.py
from flask import Flask
from microjobs.routes import bp as jobs_bp
from microjobs.auth import bp as auth_bp
from microjobs.accounts import bp as account_bp

def create_app():
    app = Flask(__name__)
    app.secret_key = "dev-secret"   # change in production

    # Register blueprints
    app.register_blueprint(jobs_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(account_bp) 

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
