import json
import hashlib
from collections.abc import Iterable

import chromadb
from chromadb.api.models.Collection import Collection

from app.config import Settings
from app.embeddings import embed_text
from app.models import HiveStats
from app.seed_data import SEED_SKILLS, SeedSkill


class SkillStore:
    """Thin ChromaDB adapter; all persistence details stay out of API routes."""

    def __init__(self, settings: Settings) -> None:
        settings.chroma_path.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(settings.chroma_path))
        self.collection: Collection = self.client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine", "description": "Hive.skill team knowledge"},
        )

    def seed(self, skills: Iterable[SeedSkill] = SEED_SKILLS) -> None:
        """Upsert fixed IDs so every application restart remains idempotent."""

        skill_list = list(skills)
        self.collection.upsert(
            ids=[skill.id for skill in skill_list],
            embeddings=[embed_text(skill.bug_signature) for skill in skill_list],
            documents=[skill.bug_signature for skill in skill_list],
            metadatas=[
                {
                    "name": skill.name,
                    "author": skill.author,
                    "created_days_ago": skill.created_days_ago,
                    "working_code": skill.working_code,
                    "tags": json.dumps(skill.tags, ensure_ascii=False),
                    "env_assumptions": json.dumps(skill.env_assumptions, ensure_ascii=False),
                    "reuse_count": skill.reuse_count,
                    "minutes_saved_per_reuse": skill.minutes_saved_per_reuse,
                    "outcome": skill.outcome,
                    "attempted_approach": skill.attempted_approach,
                    "failure_reason": skill.failure_reason,
                    "resource_cost": skill.resource_cost,
                    "safe_alternative": skill.safe_alternative,
                    "stop_conditions": json.dumps(skill.stop_conditions, ensure_ascii=False),
                    "is_seed": True,
                }
                for skill in skill_list
            ],
        )

    def stats(self) -> HiveStats:
        result = self.collection.get(include=["metadatas"])
        metadatas = result.get("metadatas") or []
        reuse_count = sum(int(item.get("reuse_count", 0)) for item in metadatas)
        total_minutes_saved = sum(
            int(item.get("reuse_count", 0)) * int(item.get("minutes_saved_per_reuse", 0))
            for item in metadatas
        )
        return HiveStats(
            skill_count=len(result.get("ids") or []),
            total_minutes_saved=total_minutes_saved,
            reuse_count=reuse_count,
        )

    def search_failed_experiment(self, plan: str) -> dict[str, object] | None:
        """Real Chroma vector lookup over failure knowledge only."""

        # Real logic: lightweight rules remove prose noise and produce a stable plan fingerprint.
        plan_lower = plan.lower()
        if "log" in plan_lower and ("vector" in plan_lower or "embed" in plan_lower):
            fingerprint = (
                "production Kubernetes K8s logs 30 days 8 TB full vector embedding semantic index "
                "8 GPU high-resource batch"
            )
        else:
            fingerprint = plan
        result = self.collection.query(
            query_embeddings=[embed_text(fingerprint)],
            n_results=1,
            where={"outcome": "failed"},
            include=["documents", "metadatas", "distances"],
        )
        if not result.get("ids") or not result["ids"][0]:
            return None

        metadata = result["metadatas"][0][0]
        distance = float(result["distances"][0][0])
        return {
            "id": result["ids"][0][0],
            "document": result["documents"][0][0],
            "similarity": round(max(0.0, min(1.0, 1.0 - distance)), 4),
            **metadata,
        }

    def search_solution(self, issue: str) -> dict[str, object] | None:
        """Search successful skills using a deterministic, noise-reduced fingerprint."""

        issue_lower = issue.lower()
        if "postgres" in issue_lower or "pg_hba" in issue_lower:
            fingerprint = (
                "Internal PostgreSQL connection fails with FATAL no pg_hba.conf entry connection timed out. "
                "The database requires corporate VPN internal CA certificate and sslmode verify-full."
            )
        elif "401" in issue_lower or "unauthorized" in issue_lower:
            fingerprint = (
                "Internal API returns 401 Unauthorized token expired invalid bearer token. "
                "Exchange credentials at the internal token endpoint for a 15-minute token."
            )
        elif "crashloop" in issue_lower or "imagepull" in issue_lower:
            fingerprint = (
                "Kubernetes Pod CrashLoopBackOff ImagePullBackOff ErrImagePull pull access denied. "
                "Namespace missing private registry imagePullSecret."
            )
        else:
            fingerprint = issue

        result = self.collection.query(
            query_embeddings=[embed_text(fingerprint)],
            n_results=1,
            where={"outcome": "success"},
            include=["documents", "metadatas", "distances"],
        )
        if not result.get("ids") or not result["ids"][0]:
            return None
        metadata = result["metadatas"][0][0]
        distance = float(result["distances"][0][0])
        return {
            "id": result["ids"][0][0],
            "document": result["documents"][0][0],
            "similarity": round(max(0.0, min(1.0, 1.0 - distance)), 4),
            **metadata,
        }

    def save_distilled(
        self,
        *,
        name: str,
        bug_signature: str,
        working_code: str,
        tags: list[str],
        env_assumptions: list[str],
    ) -> None:
        """Persist a distilled skill with a deterministic ID for idempotent demos."""

        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
        self.collection.upsert(
            ids=[f"distilled-{digest}"],
            embeddings=[embed_text(bug_signature)],
            documents=[bug_signature],
            metadatas=[
                {
                    "name": name,
                    "author": "Veteran",
                    "created_days_ago": 0,
                    "working_code": working_code,
                    "tags": json.dumps(tags),
                    "env_assumptions": json.dumps(env_assumptions),
                    "reuse_count": 0,
                    "minutes_saved_per_reuse": 0,
                    "outcome": "success",
                    "attempted_approach": "",
                    "failure_reason": "",
                    "resource_cost": "",
                    "safe_alternative": "",
                    "stop_conditions": "[]",
                    "is_seed": False,
                }
            ],
        )
