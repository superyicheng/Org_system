import json
import unittest
from unittest.mock import MagicMock, patch

from app.config import Settings
from app.llm_client import LLMClient


class LLMClientTest(unittest.TestCase):
    def test_live_client_calls_responses_api_and_records_provider(self) -> None:
        settings = Settings(
            database_url="sqlite:///:memory:",
            auth_mode="demo",
            google_client_id="",
            google_workspace_domain="",
            admin_emails=frozenset(),
            allowed_emails=frozenset(),
            session_secret="",
            public_url="http://127.0.0.1:8000",
            allowed_origins=("http://127.0.0.1:8000",),
            llm_mode="openai",
            openai_api_key="test-key-never-sent",
            openai_model="gpt-5.6-terra",
        )
        client = LLMClient(settings)
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "output": [{
                "content": [{"type": "output_text", "text": "TCP is reliable; UDP favors speed."}],
            }],
        }).encode("utf-8")

        with patch("app.llm_client.urlopen", return_value=response) as mocked_urlopen:
            answer = client.generate(
                instructions="Answer directly.",
                prompt="TCP vs UDP?",
                fallback="offline",
            )

        self.assertEqual(answer, "TCP is reliable; UDP favors speed.")
        self.assertEqual(client.last_provider, "openai:gpt-5.6-terra")
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "gpt-5.6-terra")
        self.assertEqual(payload["instructions"], "Answer directly.")
        self.assertEqual(payload["input"], "TCP vs UDP?")


if __name__ == "__main__":
    unittest.main()
