"""A local SYNAPSE-compatible store: episodic records plus light graph activation.

The interface intentionally stays independent of SQLite.  A graph/vector backend can
replace it later without changing capture, verification, serving, or the UI.
"""

from __future__ import annotations

import json
import hashlib
import re
import uuid
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from app.auth import token_digest
from app.config import Settings
from app.seed_data import demo_experiences
from app.semantic_index import cosine, embed


_MODULE_PATH = Path(__file__).resolve()
for _schema_root in (_MODULE_PATH.parents[2], _MODULE_PATH.parents[1]):
    _candidate_schema = _schema_root / "schemas" / "experience_asset.schema.json"
    if _candidate_schema.exists():
        SCHEMA_PATH = _candidate_schema
        break
else:  # Fail with a useful error if a deployment image omits the schema contract.
    SCHEMA_PATH = _MODULE_PATH.parents[1] / "schemas" / "experience_asset.schema.json"
SCHEMA_VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "that", "the", "to", "with",
}


def now() -> str:
    return datetime.now(UTC).isoformat()


def content_hash(experience: dict[str, Any]) -> str:
    canonical = json.dumps(experience, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def validate_asset(experience: dict[str, Any]) -> None:
    errors = sorted(SCHEMA_VALIDATOR.iter_errors(experience), key=lambda error: list(error.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path) or "root"
        raise ValueError(f"Experience schema violation at {location}: {error.message}")


def tokens(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9][a-z0-9_-]{1,}", value.lower()) if word not in STOP_WORDS}


def actor_name(item: dict[str, Any]) -> str:
    actor = item["actor"]
    return actor.get("display_name") or actor["id"] if isinstance(actor, dict) else str(actor)


def actor_key(item: dict[str, Any]) -> str:
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
        "captured_by": item.get("captured_by", raw_source.get("captured_by", "org.system capture")),
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
    def __init__(self, settings: Settings | Path) -> None:
        # Path support keeps the store convenient for isolated tests and tools.
        self.database_url = settings.database_url if isinstance(settings, Settings) else f"sqlite:///{settings}"
        if self.database_url.startswith("sqlite:///"):
            Path(self.database_url.removeprefix("sqlite:///")) .parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if self.database_url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(self.database_url, pool_pre_ping=True, connect_args=connect_args)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[Connection]:
        with self.engine.begin() as connection:
            yield connection

    def _initialize(self) -> None:
        statements = [
            "CREATE TABLE IF NOT EXISTS experiences (id TEXT PRIMARY KEY, payload TEXT NOT NULL, content_hash TEXT NOT NULL DEFAULT '', captured_at TEXT NOT NULL, created_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS usage_events (id TEXT PRIMARY KEY, experience_id TEXT NOT NULL, consumer TEXT NOT NULL, query TEXT NOT NULL, served_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS capture_events (id TEXT PRIMARY KEY, experience_id TEXT NOT NULL, event_type TEXT NOT NULL, detail TEXT NOT NULL, happened_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS experience_vectors (experience_id TEXT PRIMARY KEY, vector TEXT NOT NULL, indexed_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS gateway_events (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, actor TEXT NOT NULL, event_type TEXT NOT NULL, tool_name TEXT NOT NULL, tool_call TEXT NOT NULL, result TEXT NOT NULL, succeeded INTEGER NOT NULL, happened_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS users (email TEXT PRIMARY KEY, display_name TEXT NOT NULL, role TEXT NOT NULL, updated_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS mcp_tokens (id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE, owner_email TEXT NOT NULL, label TEXT NOT NULL, created_at TEXT NOT NULL, revoked_at TEXT)",
        ]
        with self._connection() as conn:
            for statement in statements:
                conn.execute(text(statement))

    def close(self) -> None:
        """Release pooled database connections during tests and Cloud Run shutdown."""
        self.engine.dispose()

    def seed(self) -> None:
        if self.list_experiences():
            return
        for item in demo_experiences():
            self.save(item, event_type="seeded", detail="Transparent local demo fixture")

    def save(self, experience: dict[str, Any], *, event_type: str, detail: str) -> dict[str, Any]:
        experience = _normalize_asset(dict(experience))
        validate_asset(experience)
        serialized = json.dumps(experience, sort_keys=True)
        digest = content_hash(experience)
        with self._connection() as conn:
            values = {"id": experience["id"], "payload": serialized, "content_hash": digest, "captured_at": experience["captured_at"], "created_at": now()}
            updated = conn.execute(text("UPDATE experiences SET payload=:payload, content_hash=:content_hash, captured_at=:captured_at, created_at=:created_at WHERE id=:id"), values)
            if not updated.rowcount:
                conn.execute(text("INSERT INTO experiences (id, payload, content_hash, captured_at, created_at) VALUES (:id, :payload, :content_hash, :captured_at, :created_at)"), values)
            conn.execute(text("INSERT INTO capture_events (id, experience_id, event_type, detail, happened_at) VALUES (:id, :experience_id, :event_type, :detail, :happened_at)"), {"id": uuid.uuid4().hex, "experience_id": experience["id"], "event_type": event_type, "detail": detail, "happened_at": now()})
            searchable = " ".join([
                task_goal(experience), experience.get("trace_summary", ""),
                experience.get("content", {}).get("what_worked", ""),
                experience.get("content", {}).get("what_failed", ""),
                " ".join(experience.get("tags", [])),
            ])
            vector_values = {"experience_id": experience["id"], "vector": json.dumps(embed(searchable)), "indexed_at": now()}
            vector_updated = conn.execute(text("UPDATE experience_vectors SET vector=:vector, indexed_at=:indexed_at WHERE experience_id=:experience_id"), vector_values)
            if not vector_updated.rowcount:
                conn.execute(text("INSERT INTO experience_vectors (experience_id, vector, indexed_at) VALUES (:experience_id, :vector, :indexed_at)"), vector_values)
        return experience

    def get(self, experience_id: str) -> dict[str, Any] | None:
        with self._connection() as conn:
            row = conn.execute(text("SELECT payload FROM experiences WHERE id=:id"), {"id": experience_id}).mappings().first()
        return json.loads(row["payload"]) if row else None

    def hash_for(self, experience_id: str) -> str | None:
        with self._connection() as conn:
            row = conn.execute(text("SELECT content_hash FROM experiences WHERE id=:id"), {"id": experience_id}).mappings().first()
        return str(row["content_hash"]) if row else None

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
            "source": {"tool_name": payload["tool_name"], "captured_by": "org.system capture"},
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
        event_type = "verified" if experience["status"] == "verified" else experience["status"]
        return self.save(experience, event_type=event_type, detail=experience["verification"]["detail"])

    def _permitted(self, item: dict[str, Any], consumer: str) -> bool:
        visibility = item["visibility"]
        return bool(visibility["consent"].get("opt_in")) and (visibility["scope"] in {"team", "org"} or actor_key(item) == consumer.lower())

    def recall(self, *, query: str, consumer: str, limit: int, record_usage: bool) -> list[dict[str, Any]]:
        query_terms = tokens(query)
        query_vector = embed(query)
        candidates = [
            item for item in self.list_experiences(include_nonserveable=False)
            if self._permitted(item, consumer)
        ]
        with self._connection() as conn:
            vector_rows = conn.execute(text("SELECT experience_id, vector FROM experience_vectors")).mappings().all()
        vectors = {row["experience_id"]: json.loads(row["vector"]) for row in vector_rows}
        ranked: list[tuple[float, dict[str, Any], list[str], float, float]] = []
        for item in candidates:
            searchable = " ".join([
                task_goal(item), item["trace_summary"], item["content"].get("what_worked", ""), " ".join(item.get("tags", [])),
            ])
            direct = query_terms & tokens(searchable)
            tag_hits = query_terms & set(item.get("tags", []))
            lexical_score = len(direct) / max(len(query_terms), 1)
            vector_score = cosine(query_vector, vectors.get(item["id"], embed(searchable)))
            score = (0.35 * lexical_score) + (0.65 * vector_score)
            # Fail closed on weak similarity: an honest no-match is safer than
            # presenting an unrelated team experience as precedent.
            if score >= 0.18:
                activation_path = [f"lexical:{term}" for term in sorted(direct)]
                activation_path += [f"tag:{tag}" for tag in sorted(tag_hits)]
                activation_path.append(f"vector:cosine={vector_score:.3f}")
                ranked.append((round(score, 3), item, activation_path, lexical_score, vector_score))
        ranked.sort(key=lambda row: (row[0], row[1]["captured_at"]), reverse=True)
        results = []
        for score, item, activation_path, lexical_score, vector_score in ranked[:limit]:
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
                "match_breakdown": {"lexical": round(lexical_score, 3), "semantic_vector": round(vector_score, 3)},
                "reuse_recipe": item.get("domain_extension", {}).get("reuse_recipe"),
                "asset_hash": self.hash_for(item["id"]),
                "resource_evidence": item.get("domain_extension", {}).get("resource_evidence", {}),
            }
            results.append(receipt)
            # Only the top receipt is actually injected into the answer. Counting
            # every ranked candidate would inflate impact and attribution.
            if record_usage and len(results) == 1:
                self.record_usage(item["id"], consumer, query)
        return results

    def record_usage(self, experience_id: str, consumer: str, query: str) -> None:
        with self._connection() as conn:
            row = conn.execute(text("SELECT payload FROM experiences WHERE id=:id"), {"id": experience_id}).mappings().first()
            if row:
                item = json.loads(row["payload"])
                item["usage"]["times_served"] += 1
                item["usage"]["last_served_at"] = now()
                if consumer not in item["usage"]["served_to"]:
                    item["usage"]["served_to"].append(consumer)
                conn.execute(text("UPDATE experiences SET payload=:payload WHERE id=:id"), {"payload": json.dumps(item, sort_keys=True), "id": experience_id})
            conn.execute(text("INSERT INTO usage_events (id, experience_id, consumer, query, served_at) VALUES (:id, :experience_id, :consumer, :query, :served_at)"), {"id": uuid.uuid4().hex, "experience_id": experience_id, "consumer": consumer, "query": query, "served_at": now()})

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
            "engine": "SYNAPSE-compatible graph (shared PostgreSQL or local SQLite, with semantic vectors)",
            "total_experiences": len(items),
            "status_counts": dict(status_counts),
            "visibility_counts": dict(visibility_counts),
            "contribution_by_member": [{"actor": actor, "count": count} for actor, count in contributions.most_common()],
            "reverify_queue": due,
            "capture_events": self.capture_events(limit=8),
            "verified_reuse_events": sum(item.get("usage", {}).get("times_served", 0) for item in items if item["status"] == "verified"),
        }

    def reverify_due(self) -> list[dict[str, Any]]:
        return self.admin_dashboard()["reverify_queue"]

    def capture_events(self, *, limit: int) -> list[dict[str, str]]:
        with self._connection() as conn:
            rows = conn.execute(text("SELECT experience_id, event_type, detail, happened_at FROM capture_events ORDER BY happened_at DESC LIMIT :limit"), {"limit": limit}).mappings().all()
        return [dict(row) for row in rows]

    def record_gateway_event(self, event: dict[str, Any]) -> dict[str, Any]:
        event_id = f"gw-{uuid.uuid4().hex[:12]}"
        happened_at = now()
        with self._connection() as conn:
            conn.execute(text("""INSERT INTO gateway_events
                (id, session_id, actor, event_type, tool_name, tool_call, result, succeeded, happened_at)
                VALUES (:id, :session_id, :actor, :event_type, :tool_name, :tool_call, :result, :succeeded, :happened_at)"""), {
                    "id": event_id, "session_id": event["session_id"], "actor": actor_name({"actor": event["actor"]}),
                    "event_type": event["event_type"], "tool_name": event["tool_name"], "tool_call": event["tool_call"],
                    "result": event["result"], "succeeded": int(event["succeeded"]), "happened_at": happened_at,
                })
        return {"id": event_id, "session_id": event["session_id"], "event_type": event["event_type"], "happened_at": happened_at}

    def impact_dashboard(self) -> dict[str, Any]:
        items = self.list_experiences()
        reuse_events = sum(item.get("usage", {}).get("times_served", 0) for item in items)
        avoided_gpu_hours = 0.0
        intercepted = 0
        for item in items:
            uses = item.get("usage", {}).get("times_served", 0)
            evidence = item.get("domain_extension", {}).get("resource_evidence", {})
            if uses and evidence.get("gpu_hours") is not None and item.get("outcome", {}).get("status") == "failure":
                avoided_gpu_hours += float(evidence["gpu_hours"]) * uses
                intercepted += uses
        return {
            "verified_experiences": sum(item["status"] == "verified" for item in items),
            "reuse_events": reuse_events,
            "duplicate_jobs_intercepted": intercepted,
            "gpu_hours_avoided": round(avoided_gpu_hours, 1),
            "method": "Sum of recorded reuse events × verified resource evidence; demo fixtures are labelled.",
        }

    def reset_demo(self) -> None:
        with self._connection() as conn:
            conn.execute(text("DELETE FROM usage_events"))
            conn.execute(text("DELETE FROM capture_events"))
            conn.execute(text("DELETE FROM experience_vectors"))
            conn.execute(text("DELETE FROM gateway_events"))
            conn.execute(text("DELETE FROM experiences"))
        self.seed()

    def upsert_user(self, *, email: str, display_name: str, role: str) -> None:
        values = {"email": email, "display_name": display_name, "role": role, "updated_at": now()}
        with self._connection() as conn:
            updated = conn.execute(text("UPDATE users SET display_name=:display_name, role=:role, updated_at=:updated_at WHERE email=:email"), values)
            if not updated.rowcount:
                conn.execute(text("INSERT INTO users (email, display_name, role, updated_at) VALUES (:email, :display_name, :role, :updated_at)"), values)

    def create_mcp_token(self, *, owner_email: str, label: str, raw_token: str) -> str:
        token_id = f"mcp-{uuid.uuid4().hex}"
        with self._connection() as conn:
            conn.execute(text("INSERT INTO mcp_tokens (id, token_hash, owner_email, label, created_at, revoked_at) VALUES (:id, :token_hash, :owner_email, :label, :created_at, NULL)"), {"id": token_id, "token_hash": token_digest(raw_token), "owner_email": owner_email, "label": label, "created_at": now()})
        return token_id

    def list_mcp_tokens(self, *, owner_email: str | None = None) -> list[dict[str, str | None]]:
        query = "SELECT id, owner_email, label, created_at, revoked_at FROM mcp_tokens"
        params: dict[str, str] = {}
        if owner_email:
            query += " WHERE owner_email=:owner_email"
            params["owner_email"] = owner_email
        query += " ORDER BY created_at DESC"
        with self._connection() as conn:
            rows = conn.execute(text(query), params).mappings().all()
        return [dict(row) for row in rows]

    def revoke_mcp_token(self, *, token_id: str, owner_email: str | None = None) -> bool:
        query = "UPDATE mcp_tokens SET revoked_at=:revoked_at WHERE id=:id AND revoked_at IS NULL"
        params: dict[str, str] = {"id": token_id, "revoked_at": now()}
        if owner_email:
            query += " AND owner_email=:owner_email"
            params["owner_email"] = owner_email
        with self._connection() as conn:
            result = conn.execute(text(query), params)
        return bool(result.rowcount)

    def identity_for_mcp_token(self, digest: str) -> dict[str, str] | None:
        with self._connection() as conn:
            row = conn.execute(text("""SELECT u.email, u.display_name, u.role FROM mcp_tokens t
                JOIN users u ON u.email=t.owner_email WHERE t.token_hash=:digest AND t.revoked_at IS NULL"""), {"digest": digest}).mappings().first()
        return dict(row) if row else None

    def identity_for_email(self, email: str) -> dict[str, str] | None:
        with self._connection() as conn:
            row = conn.execute(text("SELECT email, display_name, role FROM users WHERE email=:email"), {"email": email}).mappings().first()
        return dict(row) if row else None
