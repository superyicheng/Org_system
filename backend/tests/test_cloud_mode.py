import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CloudModeSecurityTest(unittest.TestCase):
    def test_employee_candidate_requires_admin_and_personal_mcp_token_works(self) -> None:
        """Use a new interpreter so cached environment settings cannot mask cloud mode."""
        script = r'''
from fastapi.testclient import TestClient
from app.auth import Identity, issue_session
from app.config import get_settings
from app.main import app

settings = get_settings()
admin = issue_session(Identity('admin@example.com', 'Admin', 'admin', 'test'), settings)
employee = issue_session(Identity('employee@example.com', 'Employee', 'employee', 'test'), settings)
employee_headers = {'Authorization': f'Bearer {employee}'}

with TestClient(app) as client:
    captured = client.post('/api/capture', headers=employee_headers, json={
        'task': 'Document production cache result',
        'trace_summary': 'The measured build result completed successfully.',
        'tool_name': 'Codex', 'tags': ['ci'], 'consent': True,
    })
    assert captured.status_code == 201, captured.text
    experience_id = captured.json()['experience']['id']
    assert captured.json()['experience']['status'] == 'candidate'

    rejected = client.post(f'/api/experiences/{experience_id}/verify', headers=employee_headers,
                           json={'method': 'outcome_signal', 'evidence_confirmed': True})
    assert rejected.status_code == 403, rejected.text

    connection = client.post('/api/auth/mcp-token', headers=employee_headers, json={'label': 'test laptop'})
    assert connection.status_code == 200, connection.text
    token = connection.json()['token']
    mcp_headers = {
        'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
    }
    initialized = client.post('/mcp/', headers=mcp_headers, json={
        'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
        'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}},
    })
    assert initialized.status_code == 200, initialized.text

    verified = client.post(f'/api/experiences/{experience_id}/verify', headers={'Authorization': f'Bearer {admin}'},
                           json={'method': 'outcome_signal', 'evidence_confirmed': True})
    assert verified.status_code == 200, verified.text
    assert verified.json()['experience']['status'] == 'verified'

    invited = client.post('/api/admin/members', headers={'Authorization': f'Bearer {admin}'},
                          json={'email': 'new.employee@example.com'})
    assert invited.status_code == 201, invited.text
    invited_session = issue_session(Identity('new.employee@example.com', 'New Employee', 'employee', 'test'), settings)
    admitted = client.get('/api/auth/me', headers={'Authorization': f'Bearer {invited_session}'})
    assert admitted.status_code == 200, admitted.text
    removed = client.delete('/api/admin/members/new.employee%40example.com', headers={'Authorization': f'Bearer {admin}'})
    assert removed.status_code == 200, removed.text
    rejected_after_removal = client.get('/api/auth/me', headers={'Authorization': f'Bearer {invited_session}'})
    assert rejected_after_removal.status_code == 401, rejected_after_removal.text
print('cloud mode security: OK')
'''
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = os.environ.copy()
            environment.update({
                "AUTH_MODE": "google",
                "GOOGLE_CLIENT_ID": "test-client.apps.googleusercontent.com",
                "SESSION_SECRET": "12345678901234567890123456789012",
                "PUBLIC_URL": "https://org-system.example",
                "ALLOWED_ORIGINS": "https://org-system.example",
                "ORG_SYSTEM_ADMIN_EMAILS": "admin@example.com",
                "ORG_SYSTEM_ALLOWED_EMAILS": "employee@example.com",
                "DATABASE_URL": f"sqlite:///{Path(temporary_directory) / 'cloud.sqlite3'}",
                "ORG_SYSTEM_LLM_MODE": "mock",
            })
            result = subprocess.run(
                [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                env=environment, capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("cloud mode security: OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
