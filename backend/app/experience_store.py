"""A local SYNAPSE-compatible store: episodic records plus light graph activation.

The interface intentionally stays independent of SQLite.  A graph/vector backend can
replace it later without changing capture, verification, serving, or the UI.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from app.auth import token_digest
from app.config import Settings
from app.seed_data import demo_experiences


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "that", "the", "to", "with",
}


def now() -> str:
    return datetime.now(UTC).isoformat()


def tokens(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9][a-z0-9_-]{1,}", value.lower()) if word not in STOP_WORDS}


def actor_name(item: dict[str, Any]) -> str:
    actor = item["actor"]
    return actor.get("display_name") or actor["id"] if isinstance(actor, dict) else str(actor)


def actor_key(item: dict[str, Any]) -> str:
    """Stable actor identifier, falling back gracefully for legacy demo assets."""
    actor = item["actor"]
    return (actor.get("id") or actor.get("display_name", "")).lower() if isinstance(actor, dict) else str(actor).lower()


def task_goal(item: dict[str, Any]) -> str:
    task = item["task"]
    return task["goal"] if isinstance(task, dict) else str(task)


def _normalize_asset(item: dict[str, Any]) -> dict[str, Any]:
    """Accept compact capture input, then persist the public schema exactly."""
    if item.get("schema_version") == "0.1.0":
        return item
    raw_actor = item["actor"]
    display_name = raw_actor.get("display_name", raw_actor["id"]) if isinstance(raw_actor, dict) else str(raw_actor)
    actor_id = str(raw_actor.get("id", display_name.lower().replace(" ", "-"))).lower() if isinstance(raw_actor, dict) else display_name.lower().replace(" ", "-")
    raw_task = item["task"]
    goal = raw_task.get("goal", "") if isinstance(raw_task, dict) else str(raw_task)
    domain_extension = item.get("domain_extension", {})
    raw_source = item.get("source", {})
    tool = raw_source.get("tool", raw_source.get("tool_name", "unknown-tool"))
    raw_outcome = item.get("outcome", "unknown")
    outcome_status = raw_outcome.get("status", "unknown") if isinstance(raw_outcome, dict) else str(raw_outcome)
    if outcome_status == "failed":
        outcome_status = "failure"
    raw_verification = item.get("verification", {})
    raw_verdict = raw_verification.get("verdict", raw_verification.get("last_verdict", "UNVERIFIED"))
    verdict = {"REPRODUCED": "VERIFIED", "DIVERGED": "STALE", "ENV_BROKEN": "STALE"}.get(raw_verdict, raw_verdict)
    rationale = item.get("content", {}).get("rationale", "")
    worked = item.get("content", {}).get("what_worked", item.get("content", {}).get("claim", goal))
    failed = item.get("content", {}).get("what_failed", "")
    if outcome_status == "failure" and not failed:
        failed = item.get("trace_summary", "")
    raw_visibility = item.get("visibility", {})
    raw_consent = raw_visibility.get("consent", True)
    opted_in = raw_consent.get("opt_in", False) if isinstance(raw_consent, dict) else bool(raw_consent)
    item_id = item.get("id", f"exp-{uuid.uuid4().hex[:12]}")
    verification = {
        "method": raw_verification.get("method") or "none",
        "verdict": verdict,
        "reverify_after_days": raw_verification.get("reverify_after_days", 30),
        "detail": raw_verification.get("detail", raw_verification.get("details", "Awaiting an explicit verifier.")),
    }
    verified_at = raw_verification.get("verified_at", raw_verification.get("last_verified_at"))
    if verified_at:
        verification["verified_at"] = verified_at
    provenance = item.get("provenance", {"source_refs": [], "links": []})
    provenance = {key: value for key, value in provenance.items() if value is not None}
    usage = item.get("usage", {"times_served": 0, "served_to": []})
    usage = {key: value for key, value in usage.items() if value is not None}
    return {
        "id": item_id,
        "schema_version": "0.1.0",
        "source": {"tool": tool, "connector": raw_source.get("connector", "org-system-capture")},
        "actor": {"id": actor_id, "display_name": display_name},
        "captured_at": item.get("captured_at", now()),
        "captured_by": item.get("captured_by", raw_source.get("captured_by", "Org_system capture")),
        "task": {"goal": goal, "domain": raw_task.get("domain", domain_extension.get("domain", "general")) if isinstance(raw_task, dict) else domain_extension.get("domain", "general")},
        "trace_summary": item["trace_summary"],
        "outcome": {"status": outcome_status, "signal": "captured tool outcome"},
        "content": {"what_worked": worked, "what_failed": failed, "rationale": rationale, "artifacts": []},
        "domain_extension": domain_extension,
        "verification": verification,
        "status": item.get("status", "candidate"),
        "provenance": provenance,
        "visibility": {"scope": raw_visibility.get("scope", "team"), "consent": {"opt_in": opted_in, "captured_scope": "trace summary"}},
        "memory": {"episodic_node_id": f"episode:{item_id}", "semantic_node_ids": item.get("tags", [])},
        "usage": usage,
        "tags": item.get("tags", []),
    }


class ExperienceStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        if settings.database_url.startswith("sqlite:///"):
            Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        with self.engine.begin() as connection:
            yield connection

    def _initialize(self) -> None:
        statements = [
            """CREATE TABLE IF NOT EXISTS experiences (id TEXT PRIMARY KEY, payload TEXT NOT NULL, captured_at TEXT NOT NULL, created_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS usage_events (id TEXT PRIMARY KEY, experience_id TEXT NOT NULL, consumer TEXT NOT NULL, query TEXT NOT NULL, served_at TEXT NOT NULL, FOREIGN KEY(experience_id) REFERENCES experiences(id))""",
            """CREATE TABLE IF NOT EXISTS capture_events (id TEXT PRIMARY KEY, experience_id TEXT NOT NULL, event_type TEXT NOT NULL, detail TEXT NOT NULL, happened_at TEXT NOT NULL, FOREIGN KEY(experience_id) REFERENCES experiences(id))""",
            """CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, display_name TEXT NOT NULL, role TEXT NOT NULL, updated_at TEXT NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS mcp_tokens (id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, owner_email TEXT NOT NULL, label TEXT NOT NULL, created_at TEXT NOT NULL, revoked_at TEXT, FOREIGN KEY(owner_email) REFERENCES users(email))""",
        ]
        with self._connection() as conn:
            for statement in statements:
                conn.execute(text(statement))

    def seed(self) -> None:
        if self.list_experiences():
            return
        for item in demo_experiences():
            self.save(item, event_type="seeded", detail="Transparent local demo fixture")

    def save(self, experience: dict[str, Any], *, event_type: str, detail: str) -> dict[str, Any]:
        experience = _normalize_asset(dict(experience))
        serialized = json.dumps(experience, sort_keys=True)
        with self._connection() as conn:
            values = {
                "id": experience["id"], "payload": serialized, "captured_at": experience["captured_at"], "created_at": now(),
            }
            updated = conn.execute(text(
                "UPDATE experiences SET payload = :payload, captured_at = :captured_at, created_at = :created_at WHERE id = :id"
            ), values)
            if not updated.rowcount:
                conn.execute(text("INSERT INTO experiences (id, payload, captured_at, created_at) VALUES (:id, :payload, :captured_at, :created_at)"), values)
            conn.execute(text("INSERT INTO capture_events (id, experience_id, event_type, detail, happened_at) VALUES (:id, :experience_id, :event_type, :detail, :happened_at)"), {
                "id": uuid.uuid4().hex, "experience_id": experience["id"], "event_type": event_type, "detail": detail, "happened_at": now(),
            })
        return experience

    def get(self, experience_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(text("SELECT payload FROM experiences WHERE id = :id"), {"id": experience_id}).mappings().first()
        return json.loads(row["payload"]) if row else None

    def list_experiences(self, *, include_nonserveable: bool = True, consumer: str | None = None) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(text("SELECT payload FROM experiences ORDER BY captured_at DESC")).mappings().all()
        items = [json.loads(row["payload"]) for row in rows]
        if not include_nonserveable:
            items = [item for item in items if item["status"] == "verified"]
        return items if consumer is None else [item for item in items if self._permitted(item, consumer)]

    def create_candidate(self, payload: dict[str, Any]) -> dict[str, Any]:
        candidate = {
            "id": f"exp-{uuid.uuid4().hex[:12]}",
            "actor": payload["actor"],
            "task": payload["task"],
            "trace_summary": payload["trace_summary"],
            "source": {"tool_name": payload["tool_name"], "captured_by": "Org_system capture"},
            "content": {"claim": payload["task"], "rationale": payload.get("rationale", "")},
            "tags": sorted({tag.strip().lower() for tag in payload.get("tags", []) if tag.strip()}),
            "outcome": payload.get("outcome", "success"),
            "status": "candidate",
            "visibility": {"scope": payload.get("visibility", "team"), "consent": payload.get("consent", True)},
            "verification": {
                "method": None,
                "last_verdict": "UNVERIFIED",
                "last_verified_at": None,
                "reverify_after_days": 30,
                "details": "Awaiting an explicit verifier.",
            },
            "domain_extension": payload.get("domain_extension", {}),
            "captured_at": now(),
            "created_at": now(),
        }
        return self.save(candidate, event_type="captured", detail=f"Automatic trace capture from {payload['tool_name']}")

    def verify(self, experience_id: str, result: dict[str, Any]) -> dict[str, Any] | None:
        experience = self.get(experience_id)
        if experience is None:
            return None
        experience["status"] = result["status"]
        experience["verification"].update(result["verification"])
        return self.save(experience, event_type="verified", detail=experience["verification"]["detail"])

    def _permitted(self, item: dict[str, Any], consumer: str) -> bool:
        visibility = item["visibility"]
        return bool(visibility["consent"].get("opt_in")) and (visibility["scope"] in {"team", "org"} or actor_key(item) == consumer.lower())

    def recall(self, *, query: str, consumer: str, limit: int, record_usage: bool) -> list[dict[str, Any]]:
        query_terms = tokens(query)
        candidates = [
            item for item in self.list_experiences(include_nonserveable=False)
            if self._permitted(item, consumer)
        ]
        tag_frequencies = Counter(tag for item in candidates for tag in item.get("tags", []))
        ranked: list[tuple[float, dict[str, Any], list[str]]] = []
        for item in candidates:
            searchable = " ".join([
                task_goal(item), item["trace_summary"], item["content"].get("what_worked", ""), " ".join(item.get("tags", [])),
            ])
            direct = query_terms & tokens(searchable)
            tag_hits = query_terms & set(item.get("tags", []))
            semantic_bonus = sum(0.15 for tag in tag_hits if tag_frequencies[tag] > 1)
            score = len(direct) / max(len(query_terms), 1) + semantic_bonus
            if score > 0:
                activation_path = [f"query:{term}" for term in sorted(direct)] + [f"semantic:{tag}" for tag in sorted(tag_hits)]
                ranked.append((round(score, 3), item, activation_path))
        ranked.sort(key=lambda row: (row[0], row[1]["captured_at"]), reverse=True)
        results = []
        for score, item, activation_path in ranked[:limit]:
            receipt = {
                "experience_id": item["id"],
                "title": task_goal(item),
                "claim": item["content"].get("what_worked", ""),
                "rationale": item["content"].get("rationale", ""),
                "actor": actor_name(item),
                "captured_at": item["captured_at"],
                "status": item["status"],
                "verification": {"last_verdict": item["verification"]["verdict"], "last_verified_at": item["verification"].get("verified_at"), "details": item["verification"]["detail"]},
                "visibility": item["visibility"]["scope"],
                "tags": item.get("tags", []),
                "activation_score": score,
                "activation_path": activation_path,
                "reuse_recipe": item.get("domain_extension", {}).get("reuse_recipe"),
            }
            results.append(receipt)
            if record_usage:
                self.record_usage(item["id"], consumer, query)
        return results

    def record_usage(self, experience_id: str, consumer: str, query: str) -> None:
        with self._connection() as conn:
            row = conn.execute(text("SELECT payload FROM experiences WHERE id = :id"), {"id": experience_id}).mappings().first()
            if row:
                item = json.loads(row["payload"])
                item["usage"]["times_served"] += 1
                item["usage"]["last_served_at"] = now()
                if consumer not in item["usage"]["served_to"]:
                    item["usage"]["served_to"].append(consumer)
                conn.execute(text("UPDATE experiences SET payload = :payload WHERE id = :id"), {"payload": json.dumps(item, sort_keys=True), "id": experience_id})
            conn.execute(text("INSERT INTO usage_events (id, experience_id, consumer, query, served_at) VALUES (:id, :experience_id, :consumer, :query, :served_at)"), {
                "id": uuid.uuid4().hex, "experience_id": experience_id, "consumer": consumer, "query": query, "served_at": now(),
            })

    def user_dashboard(self, actor: str) -> dict[str, Any]:
        items = self.list_experiences()
        mine = [item for item in items if actor_name(item).lower() == actor.lower()]
        with self._connection() as conn:
            usage_rows = conn.execute(text(
                """SELECT e.payload, u.consumer, u.served_at FROM usage_events u
                   JOIN experiences e ON e.id = u.experience_id
                   ORDER BY u.served_at DESC"""
            )).mappings().all()
        contributed_uses = sum(1 for row in usage_rows if actor_name(json.loads(row["payload"])).lower() == actor.lower())
        sources: Counter[str] = Counter()
        for row in usage_rows:
            item = json.loads(row["payload"])
            if row["consumer"].lower() == actor.lower():
                sources[actor_name(item)] += 1
        return {
            "actor": actor,
            "contributed": len(mine),
            "verified": sum(item["status"] == "verified" for item in mine),
            "stale": sum(item["status"] == "stale" for item in mine),
            "times_helped_others": contributed_uses,
            "using_from": [{"actor": name, "uses": uses} for name, uses in sources.most_common()],
            "experiences": mine,
        }

    def team_dashboard(self, *, consumer: str | None = None) -> dict[str, Any]:
        items = self.list_experiences(consumer=consumer)
        knowledge: dict[str, Counter[str]] = defaultdict(Counter)
        for item in items:
            for tag in item.get("tags", []):
                knowledge[tag][actor_name(item)] += 1
        return {
            "experiences": items,
            "who_knows_what": [
                {"topic": tag, "contributors": [{"actor": actor, "count": count} for actor, count in owners.most_common()]}
                for tag, owners in sorted(knowledge.items())
            ],
        }

    def admin_dashboard(self) -> dict[str, Any]:
        items = self.list_experiences()
        status_counts = Counter(item["status"] for item in items)
        visibility_counts = Counter(item["visibility"]["scope"] for item in items)
        contributions = Counter(actor_name(item) for item in items)
        due: list[dict[str, Any]] = []
        today = datetime.now(UTC)
        for item in items:
            verified_at = item["verification"].get("verified_at")
            cadence = item["verification"].get("reverify_after_days", 30)
            if verified_at:
                try:
                    due_at = datetime.fromisoformat(verified_at) + timedelta(days=cadence)
                    if due_at <= today:
                        due.append({"id": item["id"], "task": task_goal(item), "due_at": due_at.isoformat()})
                except ValueError:
                    pass
        return {
            "engine": "SYNAPSE-compatible graph (shared PostgreSQL or local SQLite)",
            "total_experiences": len(items),
            "status_counts": dict(status_counts),
            "visibility_counts": dict(visibility_counts),
            "contribution_by_member": [{"actor": actor, "count": count} for actor, count in contributions.most_common()],
            "reverify_queue": due,
            "capture_events": self.capture_events(limit=8),
        }

    def capture_events(self, *, limit: int) -> list[dict[str, str]]:
        with self._connection() as conn:
            rows = conn.execute(text("SELECT experience_id, event_type, detail, happened_at FROM capture_events ORDER BY happened_at DESC LIMIT :limit"), {"limit": limit}).mappings().all()
        return [dict(row) for row in rows]

    def reset_demo(self) -> None:
        with self._connection() as conn:
            conn.execute(text("DELETE FROM usage_events"))
            conn.execute(text("DELETE FROM capture_events"))
            conn.execute(text("DELETE FROM experiences"))
        self.seed()

    def upsert_user(self, *, email: str, display_name: str, role: str) -> None:
        with self._connection() as conn:
            values = {
                "email": email, "display_name": display_name, "role": role, "updated_at": now(),
            }
            updated = conn.execute(text(
                "UPDATE users SET display_name = :display_name, role = :role, updated_at = :updated_at WHERE email = :email"
            ), values)
            if not updated.rowcount:
                conn.execute(text("INSERT INTO users (email, display_name, role, updated_at) VALUES (:email, :display_name, :role, :updated_at)"), values)

    def create_mcp_token(self, *, owner_email: str, label: str, raw_token: str) -> str:
        token_id = f"mcp-{uuid.uuid4().hex}"
        with self._connection() as conn:
            conn.execute(text("INSERT INTO mcp_tokens (id, token_hash, owner_email, label, created_at, revoked_at) VALUES (:id, :token_hash, :owner_email, :label, :created_at, NULL)"), {
                "id": token_id, "token_hash": token_digest(raw_token), "owner_email": owner_email, "label": label, "created_at": now(),
            })
        return token_id

    def list_mcp_tokens(self, *, owner_email: str | None = None) -> list[dict[str, str | None]]:
        query = "SELECT id, owner_email, label, created_at, revoked_at FROM mcp_tokens"
        params: dict[str, str] = {}
        if owner_email:
            query += " WHERE owner_email = :owner_email"
            params["owner_email"] = owner_email
        query += " ORDER BY created_at DESC"
        with self._connection() as conn:
            rows = conn.execute(text(query), params).mappings().all()
        return [dict(row) for row in rows]

    def revoke_mcp_token(self, *, token_id: str, owner_email: str | None = None) -> bool:
        query = "UPDATE mcp_tokens SET revoked_at = :revoked_at WHERE id = :id AND revoked_at IS NULL"
        params: dict[str, str] = {"id": token_id, "revoked_at": now()}
        if owner_email:
            query += " AND owner_email = :owner_email"
            params["owner_email"] = owner_email
        with self._connection() as conn:
            result = conn.execute(text(query), params)
        return bool(result.rowcount)

    def identity_for_mcp_token(self, digest: str) -> dict[str, str] | None:
        with self._connection() as conn:
            row = conn.execute(text(
                """SELECT u.email, u.display_name, u.role FROM mcp_tokens t
                   JOIN users u ON u.email = t.owner_email
                   WHERE t.token_hash = :digest AND t.revoked_at IS NULL"""
            ), {"digest": digest}).mappings().first()
        return dict(row) if row else None

    def identity_for_email(self, email: str) -> dict[str, str] | None:
        with self._connection() as conn:
            row = conn.execute(text("SELECT email, display_name, role FROM users WHERE email = :email"), {"email": email}).mappings().first()
        return dict(row) if row else None
