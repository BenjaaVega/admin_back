import os
from datetime import datetime, timezone
from typing import Dict

import requests
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth_service:9000")
AUDIENCE = os.getenv("AUTH_AUDIENCE", "workers-service")
ALGORITHMS = ["ES256"]

security = HTTPBearer(auto_error=True)
app = FastAPI(title="Workers Service", version="1.0")


_jwks_cache: Dict | None = None
_jwks_cache_time: float | None = None
JWKS_CACHE_SEC = 3600


def get_jwks() -> Dict:
    import time
    global _jwks_cache, _jwks_cache_time
    now = time.time()
    if _jwks_cache and _jwks_cache_time and (now - _jwks_cache_time) < JWKS_CACHE_SEC:
        return _jwks_cache
    resp = requests.get(f"{AUTH_SERVICE_URL}/.well-known/jwks.json", timeout=5)
    resp.raise_for_status()
    _jwks_cache = resp.json()
    _jwks_cache_time = now
    return _jwks_cache


def verify_access_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict:
    token = credentials.credentials
    jwks = get_jwks()
    unverified_header = jwt.get_unverified_header(token)
    rsa_key = {}
    for key in jwks.get("keys", []):
        if key.get("kid") == unverified_header.get("kid"):
            rsa_key = key
            break
    if not rsa_key:
        raise HTTPException(status_code=401, detail="Public key not found")
    try:
        payload = jwt.decode(token, rsa_key, algorithms=ALGORITHMS, audience=AUDIENCE)
        if payload.get("typ") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        return payload
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@app.post("/jobs/echo")
def echo_job(body: Dict, claims: Dict = Depends(verify_access_token)):
    return {
        "ok": True,
        "echo": body,
        "sub": claims.get("sub"),
        "time": datetime.now(timezone.utc).isoformat(),
    }


