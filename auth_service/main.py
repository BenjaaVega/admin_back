import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict, Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from jose import jwt
from jose.utils import base64url_encode

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization


class TokenRequest(BaseModel):
    client_id: str
    client_secret: str
    scope: Optional[str] = "jobs.read jobs.write"


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


def generate_ec_keypair() -> Tuple[str, Dict[str, Any]]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_key = private_key.public_key()
    numbers = public_key.public_numbers()
    x_bytes = numbers.x.to_bytes(32, "big")
    y_bytes = numbers.y.to_bytes(32, "big")

    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "x": base64url_encode(x_bytes).decode(),
        "y": base64url_encode(y_bytes).decode(),
        "use": "sig",
    }
    return private_pem, jwk


APP_ISSUER = os.getenv("AUTH_ISSUER", "https://auth.local")
ACCESS_TTL_SECONDS = int(os.getenv("AUTH_ACCESS_TTL", "7200"))
REFRESH_TTL_SECONDS = int(os.getenv("AUTH_REFRESH_TTL", "86400"))
SERVICE_ACCOUNT_ID = os.getenv("SERVICE_ACCOUNT_ID", "worker-client")
SERVICE_ACCOUNT_SECRET = os.getenv("SERVICE_ACCOUNT_SECRET", "change-me")
KEY_ID = os.getenv("AUTH_KEY_ID", "kid-1")


PRIVATE_KEY_PEM, PUBLIC_JWK = generate_ec_keypair()
PUBLIC_JWK["kid"] = KEY_ID
ALGORITHM = "ES256"

app = FastAPI(title="Auth Service", version="1.0")


def sign_jwt(subject: str, audience: str, ttl_seconds: int, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "aud": audience,
        "iss": APP_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl_seconds)).timestamp()),
        "typ": token_type,
    }
    token = jwt.encode(
        payload,
        PRIVATE_KEY_PEM,
        algorithm=ALGORITHM,
        headers={"kid": KEY_ID, "alg": ALGORITHM, "typ": "JWT"},
    )
    return token


@app.get("/.well-known/jwks.json")
def jwks():
    return {"keys": [PUBLIC_JWK]}


@app.post("/token", response_model=TokenResponse)
def issue_tokens(req: TokenRequest):
    if not (req.client_id == SERVICE_ACCOUNT_ID and req.client_secret == SERVICE_ACCOUNT_SECRET):
        raise HTTPException(status_code=401, detail="Invalid client credentials")

    audience = os.getenv("AUTH_AUDIENCE", "workers-service")
    access_token = sign_jwt(subject=req.client_id, audience=audience, ttl_seconds=ACCESS_TTL_SECONDS, token_type="access")
    refresh_token = sign_jwt(subject=req.client_id, audience=audience, ttl_seconds=REFRESH_TTL_SECONDS, token_type="refresh")
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TTL_SECONDS,
    )


@app.post("/token/refresh", response_model=TokenResponse)
def refresh_tokens(req: RefreshRequest):
    try:
        claims = jwt.get_unverified_claims(req.refresh_token)
        if claims.get("typ") != "refresh":
            raise HTTPException(status_code=400, detail="Invalid token type")
    except Exception:
        raise HTTPException(status_code=400, detail="Malformed token")

    audience = os.getenv("AUTH_AUDIENCE", "workers-service")
    access_token = sign_jwt(subject=claims.get("sub", SERVICE_ACCOUNT_ID), audience=audience, ttl_seconds=ACCESS_TTL_SECONDS, token_type="access")
    refresh_token = sign_jwt(subject=claims.get("sub", SERVICE_ACCOUNT_ID), audience=audience, ttl_seconds=REFRESH_TTL_SECONDS, token_type="refresh")
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TTL_SECONDS,
    )


