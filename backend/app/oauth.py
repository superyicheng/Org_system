"""OAuth 2.1 authorization server for org.system.

MCP clients discover this server from the 401 challenge on `/mcp/`, register
themselves dynamically (RFC 7591), and send the employee through a browser consent
screen backed by Google Sign-In. The employee picks the organization the connection
acts in, and the issued access token carries that organization for its whole life.

Only PKCE (S256) public clients are supported: an MCP client on a laptop cannot keep
a client secret, so pretending it could would be theatre rather than security.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import secrets
from typing import Any
from urllib.parse import urlencode, urlparse

from sqlalchemy import text
from sqlalchemy.engine import Engine


ACCESS_TOKEN_TTL = timedelta(hours=8)
REFRESH_TOKEN_TTL = timedelta(days=60)
CODE_TTL = timedelta(minutes=5)
SUPPORTED_SCOPES = ("org.read", "org.write")


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds").replace("+00:00", "Z")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def pkce_matches(verifier: str, challenge: str) -> bool:
    """S256 only. A plain challenge is downgrade-prone, so it is refused outright."""
    import base64

    computed = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(computed, challenge)


class OAuthError(Exception):
    """An RFC 6749 error that must be reported to the client rather than swallowed."""

    def __init__(self, code: str, description: str, status_code: int = 400) -> None:
        super().__init__(description)
        self.code = code
        self.description = description
        self.status_code = status_code


@dataclass(frozen=True)
class TokenIdentity:
    email: str
    org_id: str
    scope: str
    client_id: str


class OAuthStore:
    """Persistence for clients, authorization codes, and issued tokens."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._initialize()

    def _initialize(self) -> None:
        statements = [
            "CREATE TABLE IF NOT EXISTS oauth_clients (client_id TEXT PRIMARY KEY, client_name TEXT NOT NULL, redirect_uris TEXT NOT NULL, created_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS oauth_codes (code_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, redirect_uri TEXT NOT NULL, code_challenge TEXT NOT NULL, email TEXT NOT NULL, org_id TEXT NOT NULL, scope TEXT NOT NULL, expires_at TEXT NOT NULL, consumed INTEGER NOT NULL DEFAULT 0)",
            "CREATE TABLE IF NOT EXISTS oauth_tokens (token_hash TEXT PRIMARY KEY, kind TEXT NOT NULL, client_id TEXT NOT NULL, email TEXT NOT NULL, org_id TEXT NOT NULL, scope TEXT NOT NULL, label TEXT NOT NULL DEFAULT '', issued_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT)",
        ]
        with self.engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))

    # ------------------------------------------------------------------ clients

    def register_client(self, *, client_name: str, redirect_uris: list[str]) -> dict[str, Any]:
        for uri in redirect_uris:
            parsed = urlparse(uri)
            if parsed.scheme not in {"http", "https"} and not parsed.scheme:
                raise OAuthError("invalid_redirect_uri", "Every redirect URI must be absolute.")
            if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise OAuthError("invalid_redirect_uri", "Plain http redirect URIs are only allowed on loopback addresses.")
        client = {
            "client_id": f"oc_{secrets.token_urlsafe(16)}",
            "client_name": client_name[:120] or "MCP client",
            "redirect_uris": json.dumps(redirect_uris),
            "created_at": _stamp(_now()),
        }
        with self.engine.begin() as conn:
            conn.execute(text("INSERT INTO oauth_clients (client_id, client_name, redirect_uris, created_at) VALUES (:client_id, :client_name, :redirect_uris, :created_at)"), client)
        return {"client_id": client["client_id"], "client_name": client["client_name"], "redirect_uris": redirect_uris, "created_at": client["created_at"]}

    def client(self, client_id: str) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT client_id, client_name, redirect_uris, created_at FROM oauth_clients WHERE client_id=:client_id"), {"client_id": client_id}).mappings().first()
        if not row:
            return None
        record = dict(row)
        record["redirect_uris"] = json.loads(record["redirect_uris"])
        return record

    # -------------------------------------------------------------------- codes

    def issue_code(self, *, client_id: str, redirect_uri: str, code_challenge: str, email: str, org_id: str, scope: str) -> str:
        code = f"ocode_{secrets.token_urlsafe(24)}"
        with self.engine.begin() as conn:
            conn.execute(text("""INSERT INTO oauth_codes (code_hash, client_id, redirect_uri, code_challenge, email, org_id, scope, expires_at, consumed)
                VALUES (:code_hash, :client_id, :redirect_uri, :code_challenge, :email, :org_id, :scope, :expires_at, 0)"""), {
                "code_hash": digest(code), "client_id": client_id, "redirect_uri": redirect_uri, "code_challenge": code_challenge,
                "email": email, "org_id": org_id, "scope": scope, "expires_at": _stamp(_now() + CODE_TTL),
            })
        return code

    def consume_code(self, *, code: str, client_id: str, redirect_uri: str, verifier: str) -> dict[str, str]:
        code_hash = digest(code)
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT code_hash, client_id, redirect_uri, code_challenge, email, org_id, scope, expires_at, consumed FROM oauth_codes WHERE code_hash=:code_hash"), {"code_hash": code_hash}).mappings().first()
        if row is None:
            raise OAuthError("invalid_grant", "That authorization code is not valid.")
        # Replay of a spent code means the code may have leaked; drop every token
        # already minted from it rather than quietly issuing another one. This commits
        # in its own transaction, because raising inside the transaction that performed
        # the revocation would roll the revocation straight back.
        if int(row["consumed"]):
            with self.engine.begin() as conn:
                conn.execute(text("UPDATE oauth_tokens SET revoked_at=:revoked_at WHERE client_id=:client_id AND email=:email AND revoked_at IS NULL"), {"revoked_at": _stamp(_now()), "client_id": row["client_id"], "email": row["email"]})
            raise OAuthError("invalid_grant", "That authorization code was already used; every token from it has been revoked.")
        # Atomic claim: two concurrent exchanges cannot both win this update.
        with self.engine.begin() as conn:
            claimed = conn.execute(text("UPDATE oauth_codes SET consumed=1 WHERE code_hash=:code_hash AND consumed=0"), {"code_hash": code_hash}).rowcount
        if not claimed:
            raise OAuthError("invalid_grant", "That authorization code was already used.")
        if str(row["expires_at"]) < _stamp(_now()):
            raise OAuthError("invalid_grant", "That authorization code has expired.")
        if row["client_id"] != client_id:
            raise OAuthError("invalid_grant", "That authorization code was issued to a different client.")
        if row["redirect_uri"] != redirect_uri:
            raise OAuthError("invalid_grant", "The redirect URI does not match the authorization request.")
        if not pkce_matches(verifier, str(row["code_challenge"])):
            raise OAuthError("invalid_grant", "The PKCE code verifier does not match the challenge.")
        return {"email": str(row["email"]), "org_id": str(row["org_id"]), "scope": str(row["scope"])}

    # ------------------------------------------------------------------- tokens

    def issue_tokens(self, *, client_id: str, email: str, org_id: str, scope: str, label: str = "") -> dict[str, Any]:
        access = f"oat_{secrets.token_urlsafe(32)}"
        refresh = f"ort_{secrets.token_urlsafe(32)}"
        issued = _now()
        with self.engine.begin() as conn:
            for token, kind, ttl in ((access, "access", ACCESS_TOKEN_TTL), (refresh, "refresh", REFRESH_TOKEN_TTL)):
                conn.execute(text("""INSERT INTO oauth_tokens (token_hash, kind, client_id, email, org_id, scope, label, issued_at, expires_at, revoked_at)
                    VALUES (:token_hash, :kind, :client_id, :email, :org_id, :scope, :label, :issued_at, :expires_at, NULL)"""), {
                    "token_hash": digest(token), "kind": kind, "client_id": client_id, "email": email, "org_id": org_id,
                    "scope": scope, "label": label, "issued_at": _stamp(issued), "expires_at": _stamp(issued + ttl),
                })
        return {
            "access_token": access, "refresh_token": refresh, "token_type": "Bearer",
            "expires_in": int(ACCESS_TOKEN_TTL.total_seconds()), "scope": scope,
        }

    def identity_for_access_token(self, token: str) -> TokenIdentity | None:
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT email, org_id, scope, client_id, expires_at, revoked_at FROM oauth_tokens WHERE token_hash=:token_hash AND kind='access'"), {"token_hash": digest(token)}).mappings().first()
        if row is None or row["revoked_at"] or str(row["expires_at"]) < _stamp(_now()):
            return None
        return TokenIdentity(email=str(row["email"]), org_id=str(row["org_id"]), scope=str(row["scope"]), client_id=str(row["client_id"]))

    def rotate_refresh_token(self, *, refresh_token: str, client_id: str) -> dict[str, Any]:
        token_hash = digest(refresh_token)
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT email, org_id, scope, client_id, label, expires_at, revoked_at FROM oauth_tokens WHERE token_hash=:token_hash AND kind='refresh'"), {"token_hash": token_hash}).mappings().first()
            if row is None:
                raise OAuthError("invalid_grant", "That refresh token is not valid.")
            if row["revoked_at"] or str(row["expires_at"]) < _stamp(_now()):
                raise OAuthError("invalid_grant", "That refresh token has expired or been revoked.")
            if row["client_id"] != client_id:
                raise OAuthError("invalid_grant", "That refresh token belongs to a different client.")
            conn.execute(text("UPDATE oauth_tokens SET revoked_at=:revoked_at WHERE token_hash=:token_hash"), {"revoked_at": _stamp(_now()), "token_hash": token_hash})
        return self.issue_tokens(client_id=client_id, email=str(row["email"]), org_id=str(row["org_id"]), scope=str(row["scope"]), label=str(row["label"]))

    def connections(self, *, email: str, org_id: str | None = None) -> list[dict[str, Any]]:
        """Active MCP connections, one row per refresh token, for the connections UI."""
        query = """SELECT t.token_hash, t.client_id, t.org_id, t.label, t.issued_at, t.expires_at, c.client_name
            FROM oauth_tokens t LEFT JOIN oauth_clients c ON c.client_id = t.client_id
            WHERE t.kind='refresh' AND t.email=:email AND t.revoked_at IS NULL"""
        params: dict[str, Any] = {"email": email}
        if org_id:
            query += " AND t.org_id=:org_id"
            params["org_id"] = org_id
        with self.engine.begin() as conn:
            rows = conn.execute(text(query + " ORDER BY t.issued_at DESC"), params).mappings().all()
        return [{
            "id": str(row["token_hash"])[:16],
            "client_name": row["client_name"] or "MCP client",
            "org_id": row["org_id"],
            "label": row["label"],
            "connected_at": row["issued_at"],
            "expires_at": row["expires_at"],
        } for row in rows]

    def revoke_connection(self, *, connection_id: str, email: str) -> bool:
        """Revoke a connection by its short id, including the access tokens beside it."""
        with self.engine.begin() as conn:
            row = conn.execute(text("SELECT token_hash, client_id FROM oauth_tokens WHERE kind='refresh' AND email=:email AND revoked_at IS NULL"), {"email": email}).mappings().all()
            target = next((item for item in row if str(item["token_hash"]).startswith(connection_id)), None)
            if target is None:
                return False
            conn.execute(text("UPDATE oauth_tokens SET revoked_at=:revoked_at WHERE email=:email AND client_id=:client_id AND revoked_at IS NULL"), {"revoked_at": _stamp(_now()), "email": email, "client_id": target["client_id"]})
        return True

    def revoke_everything_for(self, email: str) -> int:
        """Used when someone leaves an organization or is removed by an administrator."""
        with self.engine.begin() as conn:
            result = conn.execute(text("UPDATE oauth_tokens SET revoked_at=:revoked_at WHERE email=:email AND revoked_at IS NULL"), {"revoked_at": _stamp(_now()), "email": email})
        return int(result.rowcount or 0)


def authorization_server_metadata(public_url: str) -> dict[str, Any]:
    return {
        "issuer": public_url,
        "authorization_endpoint": f"{public_url}/oauth/authorize",
        "token_endpoint": f"{public_url}/oauth/token",
        "registration_endpoint": f"{public_url}/oauth/register",
        "revocation_endpoint": f"{public_url}/oauth/revoke",
        "scopes_supported": list(SUPPORTED_SCOPES),
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "service_documentation": f"{public_url}/docs",
    }


def protected_resource_metadata(public_url: str) -> dict[str, Any]:
    return {
        "resource": f"{public_url}/mcp",
        "authorization_servers": [public_url],
        "scopes_supported": list(SUPPORTED_SCOPES),
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{public_url}/docs",
    }


def redirect_with(redirect_uri: str, params: dict[str, str]) -> str:
    separator = "&" if "?" in redirect_uri else "?"
    return f"{redirect_uri}{separator}{urlencode(params)}"
