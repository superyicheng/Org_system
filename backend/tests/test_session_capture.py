import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class SessionCaptureTest(unittest.TestCase):
    def test_session_context_becomes_a_reusable_experience(self) -> None:
        """A raw AI session is distilled, stored in the caller's org, and served back."""
        script = r'''
import json
from fastapi.testclient import TestClient
from app.main import app

MCP = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json',
       'Authorization': 'Bearer demo'}


def call(client, name, arguments, request_id=1):
    response = client.post('/mcp/', headers=MCP, json={
        'jsonrpc': '2.0', 'id': request_id, 'method': 'tools/call',
        'params': {'name': name, 'arguments': arguments}})
    assert response.status_code == 200, response.text
    for line in response.text.splitlines():
        if line.startswith('data: '):
            payload = json.loads(line[6:])
            assert 'error' not in payload, payload
            return json.loads(payload['result']['content'][0]['text'])
    raise AssertionError('no MCP result: ' + response.text)


with TestClient(app) as client:
    listed = client.post('/mcp/', headers=MCP, json={'jsonrpc': '2.0', 'id': 0, 'method': 'tools/list', 'params': {}})
    names = [tool['name'] for line in listed.text.splitlines() if line.startswith('data: ')
             for tool in json.loads(line[6:])['result']['tools']]
    assert 'capture_session_context' in names, names

    captured = call(client, 'capture_session_context', {
        'transcript': ('We rotated the Postgres connection pooler during the incident. Raising max_connections '
                       'did nothing. Moving to a transaction-scoped pgbouncer pool cut p99 latency from 900ms '
                       'to 120ms across two hours of production traffic.'),
        'tags': ['postgres'],
    })
    assert captured['experience_id'], captured
    assert captured['lesson'], captured
    assert 'postgres' in captured['tags'], captured
    assert captured['distilled_by'] in ('openai', 'deterministic fallback'), captured

    # Too little context must be refused rather than stored as noise.
    thin = client.post('/mcp/', headers=MCP, json={
        'jsonrpc': '2.0', 'id': 9, 'method': 'tools/call',
        'params': {'name': 'capture_session_context', 'arguments': {'transcript': 'it worked'}}})
    assert 'Provide enough session context' in thin.text, thin.text

    # The captured lesson is now reachable by the pre-flight check.
    found = call(client, 'avoid_duplicate_work', {'proposal': 'tune the postgres connection pooler for latency'}, 2)
    assert found['matched'], found
    assert any(r['experience_id'] == captured['experience_id'] for r in found['verified_receipts']), found
print('session capture: OK')
'''
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = os.environ.copy()
            environment.update({
                'AUTH_MODE': 'demo',
                'PUBLIC_URL': 'http://testserver',
                'ALLOWED_ORIGINS': 'http://testserver',
                'DATABASE_URL': f"sqlite:///{Path(temporary_directory) / 'capture.sqlite3'}",
                'ORG_SYSTEM_LLM_MODE': 'mock',
            })
            result = subprocess.run(
                [sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                env=environment, capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn('session capture: OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
