import base64
import hashlib
import hmac
import json
import time
from typing import Any
from fastapi import Header, HTTPException
from src.config import get_settings

def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

def _b64url_decode(raw: str) -> bytes:
    padded = raw + "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))

def jwt_encode(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(sig)}"

def jwt_decode(token: str, secret: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise ValueError("invalid token")
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    actual = _b64url_decode(sig_b64)
    if not hmac.compare_digest(expected, actual):
        raise ValueError("bad signature")
    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    exp = payload.get("exp")
    if isinstance(exp, int) and int(time.time()) > exp:
        raise ValueError("token expired")
    return payload

def get_current_user(authorization: str | None = Header(None)) -> str:
    s = get_settings()
    if not authorization:
        raise HTTPException(status_code=401, detail="missing authorization")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="invalid authorization")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt_decode(token, s.jwt_secret)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token")
    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise HTTPException(status_code=401, detail="invalid token")
    return sub
