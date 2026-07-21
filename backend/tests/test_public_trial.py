import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PublicTrialIsolationTest(unittest.TestCase):
    def test_each_google_visitor_gets_a_private_empty_memory(self) -> None:
        """Public mode accepts any Google identity but never shares their records."""
        script = r'''
from fastapi.testclient import TestClient
from app.auth import Identity, issue_session
from app.config import get_settings
from app.main import app

settings = get_settings()

with TestClient(app) as client:
    # A public-trial visitor is admitted to the shared trial organization at sign-in.
    # Isolation between visitors comes from personal-only scoping, not from separate
    # organizations, so this test still proves Alice and Bob cannot see each other.
    store = app.state.store
    org_id = store.default_organization()['id']
    for email, display_name in (('alice@example.com', 'Alice'), ('bob@example.com', 'Bob')):
        store.upsert_user(email=email, display_name=display_name, role='employee')
        store.add_member(org_id=org_id, email=email, role='employee')
    alice = issue_session(Identity('alice@example.com', 'Alice', 'employee', 'test', org_id), settings)
    bob = issue_session(Identity('bob@example.com', 'Bob', 'employee', 'test', org_id), settings)
    alice_headers = {'Authorization': f'Bearer {alice}'}
    bob_headers = {'Authorization': f'Bearer {bob}'}

    assert client.get('/api/experiences', headers=alice_headers).json()['experiences'] == []
    captured = client.post('/api/capture', headers=alice_headers, json={
        'task': 'Measure a private cache experiment',
        'trace_summary': 'The cache reduced our test suite by 42 seconds.',
        'tool_name': 'Codex', 'tags': ['cache'], 'visibility': 'team', 'consent': True,
    })
    assert captured.status_code == 201, captured.text
    experience = captured.json()['experience']
    assert experience['visibility']['scope'] == 'private'

    verified = client.post(f"/api/experiences/{experience['id']}/verify", headers=alice_headers,
                           json={'method': 'outcome_signal', 'evidence_confirmed': True})
    assert verified.status_code == 200, verified.text
    assert verified.json()['experience']['status'] == 'verified'

    bob_list = client.get('/api/experiences', headers=bob_headers)
    assert bob_list.status_code == 200, bob_list.text
    assert bob_list.json()['experiences'] == []
    bob_recall = client.post('/api/recall', headers=bob_headers, json={'query': 'private cache experiment'})
    assert bob_recall.status_code == 200, bob_recall.text
    assert bob_recall.json()['receipts'] == []
    assert client.post(f"/api/experiences/{experience['id']}/verify", headers=bob_headers,
                       json={'method': 'outcome_signal', 'evidence_confirmed': True}).status_code == 403

    alice_recall = client.post('/api/recall', headers=alice_headers, json={'query': 'private cache experiment'})
    assert alice_recall.status_code == 200, alice_recall.text
    assert [receipt['experience_id'] for receipt in alice_recall.json()['receipts']] == [experience['id']]

    connections = client.get('/api/auth/connections', headers=alice_headers)
    assert connections.status_code == 200, connections.text
    assert connections.json()['connections'] == [], connections.text
print('public trial isolation: OK')
'''
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = os.environ.copy()
            environment.update({
                'AUTH_MODE': 'public',
                'GOOGLE_CLIENT_ID': 'test-client.apps.googleusercontent.com',
                'SESSION_SECRET': '12345678901234567890123456789012',
                'PUBLIC_URL': 'https://trial.example',
                'ALLOWED_ORIGINS': 'https://trial.example',
                'ORG_SYSTEM_ADMIN_EMAILS': '',
                'ORG_SYSTEM_ALLOWED_EMAILS': '',
                'DATABASE_URL': f"sqlite:///{Path(temporary_directory) / 'public.sqlite3'}",
                'ORG_SYSTEM_LLM_MODE': 'mock',
            })
            result = subprocess.run(
                [sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                env=environment, capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn('public trial isolation: OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
