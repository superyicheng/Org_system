"""A local SYNAPSE-compatible store: episodic records plus light graph activation.

The interface intentionally stays independent of SQLite.  A graph/vector backend can
replace it later without changing capture, verification, serving, or the UI.
"""

from __future__ import annotations

import json
import hashlib
import re
import secrets
import uuid
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from jsonschema import Draft202012Validator
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

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

# Cost dimensions a reused negative result can avoid, mapped to their dashboard
# field. Work is not only GPU-shaped: bench time is a real, scarce resource, and
# a screen that burns six wet-lab days deserves the same accounting as a job that
# burns GPU-hours. Add a dimension here and it flows to the dashboards and lineage.
AVOIDED_COST_EVIDENCE = {
    "gpu_hours": "gpu_hours_avoided",
    "wet_lab_days": "wet_lab_days_avoided",
}

AVOIDED_COST_UNITS = {"gpu_hours": "GPUh", "wet_lab_days": "wet-lab days"}


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


def slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.strip().lower())).strip("-")


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
            "CREATE TABLE IF NOT EXISTS organizations (id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE, created_by TEXT NOT NULL, created_at TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS memberships (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL, status TEXT NOT NULL, joined_at TEXT NOT NULL, UNIQUE (org_id, email))",
            "CREATE TABLE IF NOT EXISTS org_invites (code TEXT PRIMARY KEY, org_id TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, max_uses INTEGER NOT NULL, used_count INTEGER NOT NULL DEFAULT 0, revoked_at TEXT)",
        ]
        with self._connection() as conn:
            for statement in statements:
                conn.execute(text(statement))
        self._migrate_organizations()

    def _migrate_organizations(self) -> None:
        """Add org ownership to existing deployments without rewriting stored assets.

        org_id is a column rather than a payload field on purpose: the content hash is
        a receipt over the experience itself, and moving a record between organizations
        must not invalidate the receipt teammates have already seen.
        """
        with self._connection() as conn:
            existing = conn.execute(text("SELECT * FROM experiences LIMIT 1")).keys()
            if "org_id" not in set(existing):
                conn.execute(text("ALTER TABLE experiences ADD COLUMN org_id TEXT"))

    def close(self) -> None:
        """Release pooled database connections during tests and Cloud Run shutdown."""
        self.engine.dispose()

    def seed(self) -> None:
        if self.list_experiences():
            return
        for item in demo_experiences():
            self.save(item, event_type="seeded", detail="Transparent local demo fixture")

    def save(self, experience: dict[str, Any], *, event_type: str, detail: str, org_id: str | None = None) -> dict[str, Any]:
        experience = _normalize_asset(dict(experience))
        validate_asset(experience)
        serialized = json.dumps(experience, sort_keys=True)
        digest = content_hash(experience)
        with self._connection() as conn:
            values = {"id": experience["id"], "payload": serialized, "content_hash": digest, "captured_at": experience["captured_at"], "created_at": now(), "org_id": org_id}
            # COALESCE keeps an existing owner when a re-save (for example verification)
            # does not carry the organization with it.
            updated = conn.execute(text("UPDATE experiences SET payload=:payload, content_hash=:content_hash, captured_at=:captured_at, created_at=:created_at, org_id=COALESCE(:org_id, org_id) WHERE id=:id"), values)
            if not updated.rowcount:
                conn.execute(text("INSERT INTO experiences (id, payload, content_hash, captured_at, created_at, org_id) VALUES (:id, :payload, :content_hash, :captured_at, :created_at, :org_id)"), values)
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

    def list_experiences(self, *, include_nonserveable: bool = True, consumer: str | None = None, org_id: str | None = None) -> list[dict[str, Any]]:
        """List stored experiences.

        org_id=None means "do not filter by organization" and is intended for admin,
        migration, and test callers. Every request that serves one member's memory must
        pass an explicit org_id, otherwise records leak across organizations.
        """
        query = "SELECT payload FROM experiences"
        params: dict[str, Any] = {}
        if org_id is not None:
            query += " WHERE org_id=:org_id"
            params["org_id"] = org_id
        query += " ORDER BY captured_at DESC"
        with self._connection() as conn:
            rows = conn.execute(text(query), params).mappings().all()
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
        return self.save(candidate, event_type="captured", detail=f"Automatic trace capture from {payload['tool_name']}", org_id=payload.get("org_id"))

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

    def recall(self, *, query: str, consumer: str, limit: int, record_usage: bool, personal_only: bool = False, org_id: str | None = None) -> list[dict[str, Any]]:
        query_terms = tokens(query)
        query_vector = embed(query)
        candidates = [
            item for item in self.list_experiences(include_nonserveable=False, org_id=org_id)
            if self._permitted(item, consumer) and (not personal_only or actor_key(item) == consumer.lower())
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

    def user_dashboard(self, actor: str, *, org_id: str | None = None) -> dict[str, Any]:
        items = self.list_experiences(org_id=org_id)
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

    def team_dashboard(self, *, consumer: str | None = None, personal_only: bool = False, org_id: str | None = None) -> dict[str, Any]:
        items = self.list_experiences(consumer=consumer, org_id=org_id)
        if consumer is not None:
            # An employee may see their own pending draft, but a teammate's
            # candidate is never surfaced as organizational knowledge.
            items = [item for item in items if item["status"] == "verified" or actor_key(item) == consumer.lower()]
        if personal_only and consumer is not None:
            items = [item for item in items if actor_key(item) == consumer.lower()]
        knowledge: dict[str, Counter[str]] = defaultdict(Counter)
        for item in items:
            for tag in item.get("tags", []):
                knowledge[tag][actor_name(item)] += 1
        with self._connection() as conn:
            usage_rows = conn.execute(text(
                """SELECT e.id AS experience_id, e.payload, u.consumer, u.served_at
                   FROM usage_events u JOIN experiences e ON e.id = u.experience_id
                   ORDER BY u.served_at ASC"""
            )).mappings().all()
        inheritance_links: list[dict[str, Any]] = []
        for row in usage_rows:
            item = json.loads(row["payload"])
            raw_consumer = str(row["consumer"])
            consumer_name = raw_consumer.split("@", 1)[0].replace(".", " ").replace("_", " ").title()
            evidence = item.get("domain_extension", {}).get("resource_evidence", {})
            avoided = next(
                (f"{float(evidence[key]):g} {unit} avoided" for key, unit in AVOIDED_COST_UNITS.items() if evidence.get(key) is not None),
                None,
            ) if item.get("outcome", {}).get("status") == "failure" else None
            value = (
                avoided
                or (f"{float(evidence['time_saved_minutes']):g} build min saved" if evidence.get("time_saved_minutes") is not None else "verified reuse")
            )
            inheritance_links.append({
                "source": actor_name(item),
                "consumer": consumer_name,
                "experience_id": row["experience_id"],
                "experience": task_goal(item),
                "outcome": item.get("outcome", {}).get("status", "unknown"),
                "value": value,
                "served_at": row["served_at"],
            })
        return {
            "experiences": items,
            "who_knows_what": [
                {"topic": tag, "contributors": [{"actor": actor, "count": count} for actor, count in owners.most_common()]}
                for tag, owners in sorted(knowledge.items())
            ],
            "inheritance_links": inheritance_links,
        }

    def admin_dashboard(self, *, org_id: str | None = None) -> dict[str, Any]:
        items = self.list_experiences(org_id=org_id)
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
            "pending_verification": [
                {
                    "id": item["id"], "task": task_goal(item), "actor": actor_name(item),
                    "captured_at": item["captured_at"], "trace_summary": item.get("trace_summary", ""),
                    "source_tool": item.get("source", {}).get("tool", "unknown"),
                }
                for item in items if item["status"] == "candidate"
            ],
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

    def impact_dashboard(self, *, consumer: str | None = None, org_id: str | None = None) -> dict[str, Any]:
        items = self.list_experiences(org_id=org_id)
        if consumer is not None:
            items = [item for item in items if actor_key(item) == consumer.lower()]
        reuse_events = sum(item.get("usage", {}).get("times_served", 0) for item in items)
        avoided = dict.fromkeys(AVOIDED_COST_EVIDENCE, 0.0)
        build_minutes_saved = 0.0
        intercepted = 0
        for item in items:
            uses = item.get("usage", {}).get("times_served", 0)
            if not uses:
                continue
            evidence = item.get("domain_extension", {}).get("resource_evidence", {})
            status = item.get("outcome", {}).get("status")
            if status == "failure":
                # A reused negative result avoids whichever cost the work actually
                # consumed. Wet-lab days count as much as GPU-hours; only the unit
                # differs, and a job is intercepted once regardless of how many
                # cost dimensions it recorded.
                measured = [key for key in AVOIDED_COST_EVIDENCE if evidence.get(key) is not None]
                for key in measured:
                    avoided[key] += float(evidence[key]) * uses
                if measured:
                    intercepted += uses
            elif status == "success" and evidence.get("time_saved_minutes") is not None:
                build_minutes_saved += float(evidence["time_saved_minutes"]) * uses
        return {
            "verified_experiences": sum(item["status"] == "verified" for item in items),
            "reuse_events": reuse_events,
            "duplicate_jobs_intercepted": intercepted,
            **{field: round(avoided[key], 1) for key, field in AVOIDED_COST_EVIDENCE.items()},
            "build_minutes_saved": round(build_minutes_saved, 1),
            "method": "Recorded reuse events × verified resource evidence; demo fixtures are labelled.",
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

    def member_is_allowed(self, *, email: str, configured_emails: frozenset[str]) -> bool:
        normalized = email.strip().lower()
        if normalized in configured_emails:
            return True
        with self._connection() as conn:
            row = conn.execute(text("SELECT 1 FROM users WHERE email=:email"), {"email": normalized}).first()
        return row is not None

    def list_users(self) -> list[dict[str, str]]:
        with self._connection() as conn:
            rows = conn.execute(text("SELECT email, display_name, role, updated_at FROM users ORDER BY email")).mappings().all()
        return [dict(row) for row in rows]

    def provision_employee(self, email: str) -> dict[str, str]:
        normalized = email.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Provide a valid employee email address.")
        self.upsert_user(email=normalized, display_name=normalized.split("@", 1)[0], role="employee")
        member = self.identity_for_email(normalized)
        if not member:
            raise RuntimeError("Employee provisioning did not persist.")
        return member

    def deprovision_employee(self, email: str) -> bool:
        normalized = email.strip().lower()
        with self._connection() as conn:
            result = conn.execute(text("DELETE FROM users WHERE email=:email"), {"email": normalized})
        return bool(result.rowcount)

    def identity_for_email(self, email: str) -> dict[str, str] | None:
        with self._connection() as conn:
            row = conn.execute(text("SELECT email, display_name, role FROM users WHERE email=:email"), {"email": email}).mappings().first()
        return dict(row) if row else None

    # ------------------------------------------------------------ organizations

    def create_organization(self, *, name: str, created_by: str) -> dict[str, str]:
        """Create an organization and make the creator its first admin."""
        clean_name = name.strip()
        if not 2 <= len(clean_name) <= 80:
            raise ValueError("An organization name must be between 2 and 80 characters.")
        slug = slugify(clean_name)
        if not slug:
            raise ValueError("An organization name must contain letters or numbers.")
        owner = created_by.strip().lower()
        org = {"id": f"org-{uuid.uuid4().hex[:12]}", "name": clean_name, "slug": slug, "created_by": owner, "created_at": now()}
        with self._connection() as conn:
            if conn.execute(text("SELECT 1 FROM organizations WHERE slug=:slug"), {"slug": slug}).first():
                raise ValueError(f"An organization named '{clean_name}' already exists.")
            conn.execute(text("INSERT INTO organizations (id, name, slug, created_by, created_at) VALUES (:id, :name, :slug, :created_by, :created_at)"), org)
        self.add_member(org_id=org["id"], email=owner, role="admin")
        return org

    def get_organization(self, org_id: str) -> dict[str, str] | None:
        with self._connection() as conn:
            row = conn.execute(text("SELECT id, name, slug, created_by, created_at FROM organizations WHERE id=:id"), {"id": org_id}).mappings().first()
        return dict(row) if row else None

    def list_organizations(self) -> list[dict[str, str]]:
        with self._connection() as conn:
            rows = conn.execute(text("SELECT id, name, slug, created_by, created_at FROM organizations ORDER BY created_at")).mappings().all()
        return [dict(row) for row in rows]

    def default_organization(self, *, name: str = "Default organization", created_by: str = "system@org.system") -> dict[str, str]:
        """Return the organization that pre-multi-org records and members belong to."""
        with self._connection() as conn:
            row = conn.execute(text("SELECT id, name, slug, created_by, created_at FROM organizations WHERE slug=:slug"), {"slug": "default"}).mappings().first()
        if row:
            return dict(row)
        org = {"id": f"org-{uuid.uuid4().hex[:12]}", "name": name, "slug": "default", "created_by": created_by.strip().lower(), "created_at": now()}
        with self._connection() as conn:
            conn.execute(text("INSERT INTO organizations (id, name, slug, created_by, created_at) VALUES (:id, :name, :slug, :created_by, :created_at)"), org)
        return org

    def adopt_orphans(self) -> str:
        """Move pre-multi-org experiences and users into the default org.

        Safe to call repeatedly: it only touches rows whose org is still unset.
        """
        org_id = self.default_organization()["id"]
        with self._connection() as conn:
            conn.execute(text("UPDATE experiences SET org_id=:org_id WHERE org_id IS NULL"), {"org_id": org_id})
            legacy = conn.execute(text("""SELECT u.email, u.role FROM users u
                WHERE NOT EXISTS (SELECT 1 FROM memberships m WHERE m.email = u.email)""")).mappings().all()
        for user in legacy:
            self.add_member(org_id=org_id, email=str(user["email"]), role=str(user["role"]))
        return org_id

    def add_member(self, *, org_id: str, email: str, role: str = "employee", status: str = "active") -> dict[str, str]:
        normalized = email.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Provide a valid member email address.")
        if role not in {"admin", "employee"}:
            raise ValueError("A member role must be admin or employee.")
        record = {"id": f"mem-{uuid.uuid4().hex[:12]}", "org_id": org_id, "email": normalized, "role": role, "status": status, "joined_at": now()}
        with self._connection() as conn:
            updated = conn.execute(text("UPDATE memberships SET role=:role, status=:status WHERE org_id=:org_id AND email=:email"), record)
            if not updated.rowcount:
                conn.execute(text("INSERT INTO memberships (id, org_id, email, role, status, joined_at) VALUES (:id, :org_id, :email, :role, :status, :joined_at)"), record)
        return record

    def remove_member(self, *, org_id: str, email: str) -> bool:
        with self._connection() as conn:
            result = conn.execute(text("DELETE FROM memberships WHERE org_id=:org_id AND email=:email"), {"org_id": org_id, "email": email.strip().lower()})
        return bool(result.rowcount)

    def membership_for(self, *, org_id: str, email: str) -> dict[str, str] | None:
        with self._connection() as conn:
            row = conn.execute(text("SELECT org_id, email, role, status, joined_at FROM memberships WHERE org_id=:org_id AND email=:email"), {"org_id": org_id, "email": email.strip().lower()}).mappings().first()
        return dict(row) if row else None

    def is_member(self, *, org_id: str, email: str) -> bool:
        membership = self.membership_for(org_id=org_id, email=email)
        return bool(membership and membership["status"] == "active")

    def organizations_for(self, email: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(text("""SELECT o.id, o.name, o.slug, o.created_by, o.created_at, m.role, m.status, m.joined_at
                FROM memberships m JOIN organizations o ON o.id = m.org_id
                WHERE m.email=:email ORDER BY o.created_at"""), {"email": email.strip().lower()}).mappings().all()
        return [dict(row) for row in rows]

    def org_members(self, org_id: str) -> list[dict[str, Any]]:
        """Members of an organization with how much each has contributed and how often it was reused."""
        with self._connection() as conn:
            rows = conn.execute(text("""SELECT m.email, m.role, m.status, m.joined_at, u.display_name
                FROM memberships m LEFT JOIN users u ON u.email = m.email
                WHERE m.org_id=:org_id ORDER BY m.role, m.email"""), {"org_id": org_id}).mappings().all()
        items = self.list_experiences(org_id=org_id)
        contributed: Counter[str] = Counter()
        verified: Counter[str] = Counter()
        reused: Counter[str] = Counter()
        for item in items:
            key = actor_key(item)
            contributed[key] += 1
            if item["status"] == "verified":
                verified[key] += 1
            reused[key] += int(item.get("usage", {}).get("times_served", 0))
        members = []
        for row in rows:
            email = str(row["email"])
            members.append({
                "email": email,
                "display_name": row["display_name"] or email.split("@", 1)[0],
                "role": row["role"],
                "status": row["status"],
                "joined_at": row["joined_at"],
                "experiences_contributed": contributed.get(email, 0),
                "verified_contributions": verified.get(email, 0),
                "times_reused_by_others": reused.get(email, 0),
            })
        return members

    def create_invite(self, *, org_id: str, created_by: str, ttl_hours: int = 168, max_uses: int = 25) -> dict[str, Any]:
        if not 1 <= ttl_hours <= 24 * 90:
            raise ValueError("An invite must expire between 1 hour and 90 days from now.")
        if not 1 <= max_uses <= 500:
            raise ValueError("An invite must allow between 1 and 500 uses.")
        invite = {
            "code": f"inv_{secrets.token_urlsafe(18)}",
            "org_id": org_id,
            "created_by": created_by.strip().lower(),
            "created_at": now(),
            "expires_at": (datetime.now(UTC) + timedelta(hours=ttl_hours)).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "max_uses": max_uses,
            "used_count": 0,
        }
        with self._connection() as conn:
            conn.execute(text("""INSERT INTO org_invites (code, org_id, created_by, created_at, expires_at, max_uses, used_count, revoked_at)
                VALUES (:code, :org_id, :created_by, :created_at, :expires_at, :max_uses, 0, NULL)"""), invite)
        return invite

    def list_invites(self, org_id: str) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(text("SELECT code, org_id, created_by, created_at, expires_at, max_uses, used_count, revoked_at FROM org_invites WHERE org_id=:org_id ORDER BY created_at DESC"), {"org_id": org_id}).mappings().all()
        return [dict(row) for row in rows]

    def revoke_invite(self, *, code: str, org_id: str) -> bool:
        with self._connection() as conn:
            result = conn.execute(text("UPDATE org_invites SET revoked_at=:revoked_at WHERE code=:code AND org_id=:org_id AND revoked_at IS NULL"), {"revoked_at": now(), "code": code, "org_id": org_id})
        return bool(result.rowcount)

    def redeem_invite(self, *, code: str, email: str) -> dict[str, str]:
        """Join the inviting organization, or raise ValueError explaining why not."""
        with self._connection() as conn:
            row = conn.execute(text("SELECT code, org_id, expires_at, max_uses, used_count, revoked_at FROM org_invites WHERE code=:code"), {"code": code}).mappings().first()
            if row is None:
                raise ValueError("This invite code is not valid.")
            if row["revoked_at"]:
                raise ValueError("This invite has been revoked.")
            if str(row["expires_at"]) < now():
                raise ValueError("This invite has expired.")
            if int(row["used_count"]) >= int(row["max_uses"]):
                raise ValueError("This invite has already been used the maximum number of times.")
            conn.execute(text("UPDATE org_invites SET used_count = used_count + 1 WHERE code=:code"), {"code": code})
        org_id = str(row["org_id"])
        self.add_member(org_id=org_id, email=email, role="employee")
        organization = self.get_organization(org_id)
        if organization is None:
            raise ValueError("The inviting organization no longer exists.")
        return organization
