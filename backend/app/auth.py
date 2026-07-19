"""Google browser sessions and revocable machine tokens for Codex clients."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import json
import secrets
from typing import Any

from fastapi import HTTPException, Request, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from app.config import Settings


@dataclass(frozen=True)
class Identity:
    email: str
    display_name: str
    role: str
    auth_kind: str


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_session(identity: Identity, settings: Settings) -> str:
    payload = {
        "email": identity.email,
        "display_name": identity.display_name,
        "role": identity.role,
        "exp": int((datetime.now(UTC) + timedelta(hours=8)).timestamp()),
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _encode(hmac.new(settings.session_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"oss_{encoded}.{signature}"


def decode_session(token: str, settings: Settings) -> Identity | None:
    if not token.startswith("oss_") or "." not in token[4:]:
        return None
    encoded, signature = token[4:].rsplit(".", 1)
    expected = _encode(hmac.new(settings.session_secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_decode(encoded))
        if int(payload["exp"]) < int(datetime.now(UTC).timestamp()):
            return None
        return Identity(email=payload["email"], display_name=payload["display_name"], role=payload["role"], auth_kind="browser-session")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def verify_google(credential: str, settings: Settings) -> Identity:
    try:
        claims: dict[str, Any] = id_token.verify_oauth2_token(credential, google_requests.Request(), settings.google_client_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google identity token could not be verified.") from error
    email = str(claims.get("email", "")).lower()
    if not email or not claims.get("email_verified"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="A verified Google email is required.")
    if settings.google_workspace_domain and not email.endswith(f"@{settings.google_workspace_domain}"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This Google Workspace account is not allowed.")
    return Identity(
        email=email,
        display_name=str(claims.get("name") or email.split("@", 1)[0]),
        role="admin" if email in settings.admin_emails else "employee",
        auth_kind="google",
    )


def new_machine_token() -> tuple[str, str]:
    token = f"orgmcp_{secrets.token_urlsafe(32)}"
    return token, hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def require_identity(request: Request) -> Identity:
    """Resolve identity from a cloud credential, with explicit local demo fallback."""
    settings: Settings = request.app.state.settings
    store = request.app.state.store
    if settings.is_demo:
        return Identity(email="demo@org.system", display_name="Demo User", role="admin", auth_kind="demo")
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in with Google or provide an Org_system MCP token.")
    token = authorization.removeprefix("Bearer ").strip()
    machine_identity = store.identity_for_mcp_token(token_digest(token)) if token.startswith("orgmcp_") else None
    if machine_identity:
        return Identity(email=machine_identity["email"], display_name=machine_identity["display_name"], role=machine_identity["role"], auth_kind="mcp-token")
    session_identity = decode_session(token, settings)
    if session_identity:
        return session_identity
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="The Org_system credential is invalid or expired.")


def require_admin(request: Request) -> Identity:
    identity = require_identity(request)
    if identity.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access is required.")
    return identity
