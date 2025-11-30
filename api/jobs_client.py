import os
import time
from typing import Any, Dict, Optional, Tuple

import requests


AUTH_URL = os.getenv("AUTH_SERVICE_URL", "http://auth_service:9000")
WORKERS_URL = os.getenv("WORKERS_SERVICE_URL", "http://workers_service:9100")
SERVICE_ACCOUNT_ID = os.getenv("SERVICE_ACCOUNT_ID", "worker-client")
SERVICE_ACCOUNT_SECRET = os.getenv("SERVICE_ACCOUNT_SECRET", "change-me")


class TokenPair:
    def __init__(self, access_token: str, refresh_token: str, access_exp: int):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.access_exp = access_exp


class JobsAuthClient:
    def __init__(self):
        self._tokens: Optional[TokenPair] = None

    def _decode_exp(self, token: str) -> int:
        import jwt as pyjwt  # PyJWT for exp decode only
        unverified = pyjwt.decode(token, options={"verify_signature": False, "verify_exp": False})
        return int(unverified.get("exp", 0))

    def _login(self) -> TokenPair:
        resp = requests.post(
            f"{AUTH_URL}/token",
            json={
                "client_id": SERVICE_ACCOUNT_ID,
                "client_secret": SERVICE_ACCOUNT_SECRET,
            },
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
        access_exp = self._decode_exp(data["access_token"])
        return TokenPair(data["access_token"], data["refresh_token"], access_exp)

    def _refresh(self) -> Optional[TokenPair]:
        if not self._tokens:
            return None
        resp = requests.post(
            f"{AUTH_URL}/token/refresh",
            json={"refresh_token": self._tokens.refresh_token},
            timeout=5,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        access_exp = self._decode_exp(data["access_token"])
        return TokenPair(data["access_token"], data["refresh_token"], access_exp)

    def _ensure_tokens(self):
        now = int(time.time())
        # Renew if no tokens or expiring in <60s
        if not self._tokens or (self._tokens.access_exp - now) < 60:
            # Try refresh first
            new_pair = self._refresh()
            if not new_pair:
                new_pair = self._login()
            self._tokens = new_pair

    def call_workers_echo(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_tokens()
        assert self._tokens is not None
        resp = requests.post(
            f"{WORKERS_URL}/jobs/echo",
            json=payload,
            headers={"Authorization": f"Bearer {self._tokens.access_token}"},
            timeout=5,
        )
        if resp.status_code == 401:
            # Access token likely expired or invalid; try refresh/login and retry once
            new_pair = self._refresh() or self._login()
            self._tokens = new_pair
            resp = requests.post(
                f"{WORKERS_URL}/jobs/echo",
                json=payload,
                headers={"Authorization": f"Bearer {self._tokens.access_token}"},
                timeout=5,
            )
        resp.raise_for_status()
        return resp.json()


jobs_auth_client = JobsAuthClient()


