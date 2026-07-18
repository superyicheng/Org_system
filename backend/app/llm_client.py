import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from app.config import Settings


@dataclass(frozen=True)
class LLMResult:
    text: str
    mode: str


MOCK_PREFLIGHT_TEXT = (
    "Pause this full-scale job. Sixty-two days ago, the team ran a highly similar production-log embedding experiment: "
    "roughly 8 TB of data consumed 148 GPU hours while search accuracy improved by only 3%. Your data scope, log type, "
    "and requested resources closely match that failed run, so executing now would likely repeat the same waste.\n\n"
    "A safer path is to sample one hour of logs, redact secrets, cluster error fingerprints, keep only 3–5 representatives "
    "per cluster, and validate recall with a hard six-GPU-hour cap. The executable validation script is ready on the right."
)


class LLMClient:
    """Switchable LLM adapter with a non-failing hackathon mock fallback."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _generate(self, instructions: str, input_text: str, fallback: str) -> LLMResult:
        if not self.settings.llm_api_key:
            return LLMResult(fallback, "mock")

        payload = json.dumps(
            {
                "model": self.settings.llm_model,
                "instructions": instructions,
                "input": input_text,
                "max_output_tokens": 700,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.settings.llm_base_url.rstrip('/')}/responses",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.settings.llm_timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
            chunks = [
                content.get("text", "")
                for item in data.get("output", [])
                for content in item.get("content", [])
                if content.get("type") == "output_text"
            ]
            text = "".join(chunks).strip()
            if not text:
                raise ValueError("LLM returned no output_text")
            return LLMResult(text, "live")
        except (OSError, TimeoutError, ValueError, KeyError, json.JSONDecodeError):
            # Demo boundary: LLM/API failures must never break the live flow.
            return LLMResult(fallback, "mock")

    def explain_preflight(self, plan: str, evidence: dict[str, object]) -> LLMResult:
        instructions = (
            "You are a senior FinOps and DevOps reviewer for a platform engineering team. Use the team's real failed-run "
            "record to decide whether the current plan repeats a known mistake. Write two concise, natural English paragraphs "
            "suitable for a chat bubble. The first must give a clear verdict and cite resource-cost and outcome evidence. "
            "The second must provide a lower-cost executable alternative. Do not use Markdown headings or invent facts."
        )
        input_text = (
            f"Current plan:\n{plan}\n\n"
            f"Matched prior failed-run record:\n{json.dumps(evidence, ensure_ascii=False)}"
        )
        return self._generate(instructions, input_text, MOCK_PREFLIGHT_TEXT)

    def generate_fix(self, issue: str, skill: dict[str, object]) -> LLMResult:
        fallback = str(skill["working_code"])
        instructions = (
            "You are a platform engineer. Adapt the matched team's proven fix to the current error. Return only a safe, "
            "directly executable Bash script. Preserve environment-variable placeholders and never invent credentials."
        )
        input_text = (
            f"Current error:\n{issue}\n\n"
            f"Matched skill and proven script:\n{json.dumps(skill, ensure_ascii=False)}"
        )
        return self._generate(instructions, input_text, fallback)
