"""Zero-extra-service stdio MCP entrypoint for Codex and other MCP clients."""

from __future__ import annotations

import json
import sys

from app.config import get_settings
from app.experience_store import ExperienceStore
from app.mcp_server import handle


def main() -> None:
    settings = get_settings()
    store = ExperienceStore(settings.database_path)
    store.seed()
    for line in sys.stdin:
        try:
            message = json.loads(line)
            method = message.get("method", "")
            if method.startswith("notifications/"):
                continue
            reply = handle(message.get("id"), method, message.get("params", {}), store)
        except Exception as error:  # MCP must return protocol errors, never corrupt stdout.
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(error)}}
        sys.stdout.write(json.dumps(reply, separators=(",", ":")) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
