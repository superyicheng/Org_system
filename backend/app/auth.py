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
    # The organization this credential is currently acting in. None means the user is
    # signed in but has not created or joined one yet, so no memory may be served.
    org_id: str | None = None


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_session(identity: Identity, settings: Settings) -> str:
    payload = {"email": identity.email, "display_name": identity.display_name, "role": identity.role, "org_id": identity.org_id, "exp": int((datetime.now(UTC) + timedelta(hours=8)).timestamp())}
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
        return Identity(email=payload["email"], display_name=payload["display_name"], role=payload["role"], auth_kind="browser-session", org_id=payload.get("org_id"))
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
    return Identity(email=email, display_name=str(claims.get("name") or email.split("@", 1)[0]), role="admin" if email in settings.admin_emails else "employee", auth_kind="google")


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def require_identity(request: Request) -> Identity:
    settings: Settings = request.app.state.settings
    if settings.is_demo:
        return Identity(email="demo@org.system", display_name="Demo User", role="admin", auth_kind="demo", org_id=request.app.state.store.default_organization()["id"])
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in with Google or provide an org.system Codex token.")
    token = authorization.removeprefix("Bearer ").strip()
    store = request.app.state.store
    # OAuth access tokens issued to an MCP client carry their own organization, so the
    # same credential works for the REST API without a second kind of secret existing.
    if token.startswith("oat_"):
        granted = request.app.state.oauth.identity_for_access_token(token)
        machine = store.identity_for_email(granted.email) if granted else None
        if granted and machine and store.is_member(org_id=granted.org_id, email=granted.email):
            return Identity(email=machine["email"], display_name=machine["display_name"], role=machine["role"], auth_kind="oauth", org_id=granted.org_id)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="The org.system credential is invalid or expired.")
    session = decode_session(token, settings)
    if session and (settings.is_public_trial or store.member_is_allowed(email=session.email, configured_emails=settings.admin_emails | settings.allowed_emails)):
        return session
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="The org.system credential is invalid or expired.")


def require_admin(request: Request) -> Identity:
    identity = require_identity(request)
    if identity.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access is required.")
    return identity


def require_org(request: Request) -> tuple[Identity, str]:
    """Require a credential that is acting inside an organization.

    Fails closed: a signed-in user with no organization gets no memory at all rather
    than a silent fallback to someone else's records.
    """
    identity = require_identity(request)
    if not identity.org_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Create or join an organization before using team memory.")
    store = request.app.state.store
    if identity.auth_kind != "demo" and not store.is_member(org_id=identity.org_id, email=identity.email):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are no longer a member of this organization.")
    return identity, identity.org_id
