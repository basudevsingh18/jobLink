# microjobs/security.py
import os, hmac, hashlib, base64
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import current_app

def token_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="email-verify")

def make_email_token(email: str) -> str:
    return token_serializer().dumps(email)

def read_email_token(token: str, max_age=60*60*24):  # 24h
    return token_serializer().loads(token, max_age=max_age)

def hash_token(raw: str) -> str:
    # store hash in DB instead of raw token (defense in depth)
    return base64.b64encode(hashlib.sha256(raw.encode()).digest()).decode()
