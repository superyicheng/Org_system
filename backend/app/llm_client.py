"""Small switchable LLM adapter.

REAL: when OPENAI_API_KEY is present, calls the Responses API.
DEMO-SAFE: without a key, deterministic copy is returned so the demo never stalls.
Retrieval, verification, persistence, and receipts remain real in both modes.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import Settings


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.mode = settings.llm_mode
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        self.last_provider = "deterministic_mock"

    @property
    def live(self) -> bool:
        return self.mode == "openai" and bool(self.api_key)

    def generate(self, *, instructions: str, prompt: str, fallback: str) -> str:
        if not self.live:
            self.last_provider = "deterministic_mock"
            return fallback
        body = json.dumps({
            "model": self.model,
            "instructions": instructions,
            "input": prompt,
            "max_output_tokens": 900,
        }).encode("utf-8")
        request = Request(
            "https://api.openai.com/v1/responses",
            data=body,
            method="POST",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("output_text"):
                self.last_provider = f"openai:{self.model}"
                return str(payload["output_text"]).strip()
            chunks = []
            for item in payload.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        chunks.append(content.get("text", ""))
            generated = "\n".join(chunks).strip()
            self.last_provider = f"openai:{self.model}" if generated else "deterministic_fallback"
            return generated or fallback
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError):
            # A live provider failure must never break the on-stage path.
            self.last_provider = "deterministic_fallback"
            return fallback

    def generate_json(self, *, instructions: str, prompt: str, fallback: dict[str, Any]) -> dict[str, Any]:
        raw = self.generate(instructions=instructions, prompt=prompt, fallback=json.dumps(fallback))
        try:
            start, end = raw.find("{"), raw.rfind("}")
            return json.loads(raw[start:end + 1]) if start >= 0 and end >= start else fallback
        except (json.JSONDecodeError, TypeError):
            return fallback

    def judge_experience(self, experience: dict[str, Any]) -> dict[str, Any]:
        """Apply a fixed evidence rubric; live mode asks OpenAI, mock mode is explicit."""
        content = experience.get("content", {})
        evidence = experience.get("domain_extension", {}).get("resource_evidence", {})
        fallback_score = 0.92 if (
            experience.get("trace_summary")
            and (content.get("what_worked") or content.get("what_failed"))
            and (evidence or experience.get("outcome", {}).get("signal"))
        ) else 0.58
        fallback = {
            "score": fallback_score,
            "verdict": "supported" if fallback_score >= 0.8 else "insufficient_evidence",
            "rationale": (
                "The claim has a concrete trace, an actionable lesson, and objective outcome evidence."
                if fallback_score >= 0.8 else
                "The trace is missing either an actionable lesson or objective outcome evidence."
            ),
        }
        result = self.generate_json(
            instructions=(
                "Act as a strict experience-evidence judge. Return JSON only with score (0..1), verdict, and rationale. "
                "A high score requires a concrete trace, actionable lesson, and objective outcome evidence. Do not infer missing evidence."
            ),
            prompt=json.dumps(experience, ensure_ascii=False),
            fallback=fallback,
        )
        try:
            score = min(1.0, max(0.0, float(result.get("score", fallback_score))))
        except (TypeError, ValueError):
            score = fallback_score
        return {
            "score": score,
            "verdict": str(result.get("verdict", fallback["verdict"])),
            "rationale": str(result.get("rationale", fallback["rationale"])),
            "provider": self.last_provider,
            "rubric": "trace + actionable lesson + objective outcome evidence",
        }
