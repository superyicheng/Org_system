import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def run_script(script: str, temporary_directory: str) -> subprocess.CompletedProcess[str]:
    """Run in a fresh interpreter so cached settings cannot mask multi-org mode."""
    environment = os.environ.copy()
    environment.update({
        "AUTH_MODE": "google",
        "GOOGLE_CLIENT_ID": "test-client.apps.googleusercontent.com",
        "SESSION_SECRET": "12345678901234567890123456789012",
        "PUBLIC_URL": "https://org-system.example",
        "ALLOWED_ORIGINS": "https://org-system.example",
        "ORG_SYSTEM_ADMIN_EMAILS": "",
        "ORG_SYSTEM_ALLOWED_EMAILS": "alice@acme.example,bob@globex.example,carol@acme.example,dave@nowhere.example",
        "DATABASE_URL": f"sqlite:///{Path(temporary_directory) / 'orgs.sqlite3'}",
        "ORG_SYSTEM_LLM_MODE": "mock",
        "ORG_SELF_SERVE": "true",
    })
    return subprocess.run(
        [sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
        env=environment, capture_output=True, text=True, check=False,
    )


PRELUDE = r'''
from fastapi.testclient import TestClient
from app.auth import Identity, issue_session
from app.config import get_settings
from app.main import app

settings = get_settings()


def signed_in(client, email, display_name):
    """A user who has authenticated but has not created or joined an organization."""
    app.state.store.upsert_user(email=email, display_name=display_name, role='employee')
    return {'Authorization': f"Bearer {issue_session(Identity(email, display_name, 'employee', 'test'), settings)}"}


def bearer(token):
    return {'Authorization': f'Bearer {token}'}
'''


class OrganizationIsolationTest(unittest.TestCase):
    def test_experiences_never_cross_organization_boundaries(self) -> None:
        """A verified lesson in one organization is invisible to another organization."""
        script = PRELUDE + r'''
with TestClient(app) as client:
    alice = signed_in(client, 'alice@acme.example', 'Alice')
    acme = client.post('/api/orgs', headers=alice, json={'name': 'Acme Research'})
    assert acme.status_code == 201, acme.text
    alice = bearer(acme.json()['access_token'])
    assert acme.json()['user']['role'] == 'admin', acme.text

    captured = client.post('/api/capture', headers=alice, json={
        'task': 'Measure the nightly embedding job cost',
        'trace_summary': 'Embedding the full corpus cost 148 GPU-hours for a 3 percent gain.',
        'tool_name': 'Codex', 'tags': ['embedding'], 'visibility': 'team', 'consent': True,
    })
    assert captured.status_code == 201, captured.text
    experience_id = captured.json()['experience']['id']
    verified = client.post(f'/api/experiences/{experience_id}/verify', headers=alice,
                           json={'method': 'outcome_signal', 'evidence_confirmed': True})
    assert verified.status_code == 200, verified.text

    alice_recall = client.post('/api/recall', headers=alice, json={'query': 'nightly embedding job cost'})
    assert [r['experience_id'] for r in alice_recall.json()['receipts']] == [experience_id], alice_recall.text

    bob = signed_in(client, 'bob@globex.example', 'Bob')
    globex = client.post('/api/orgs', headers=bob, json={'name': 'Globex Labs'})
    assert globex.status_code == 201, globex.text
    bob = bearer(globex.json()['access_token'])

    bob_recall = client.post('/api/recall', headers=bob, json={'query': 'nightly embedding job cost'})
    assert bob_recall.status_code == 200, bob_recall.text
    assert bob_recall.json()['receipts'] == [], bob_recall.text
    assert client.get('/api/experiences', headers=bob).json()['experiences'] == []
    assert client.get('/api/dashboard/team', headers=bob).json()['experiences'] == []
print('organization isolation: OK')
'''
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = run_script(script, temporary_directory)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn('organization isolation: OK', result.stdout)

    def test_invite_join_makes_team_memory_shared_and_counted(self) -> None:
        """An invited teammate reads verified memory, and contributions are attributed."""
        script = PRELUDE + r'''
with TestClient(app) as client:
    alice = signed_in(client, 'alice@acme.example', 'Alice')
    acme = client.post('/api/orgs', headers=alice, json={'name': 'Acme Research'})
    org_id = acme.json()['organization']['id']
    alice = bearer(acme.json()['access_token'])

    captured = client.post('/api/capture', headers=alice, json={
        'task': 'Cache the CI container layers',
        'trace_summary': 'Layer caching removed 42 seconds from every build.',
        'tool_name': 'Codex', 'tags': ['ci'], 'visibility': 'team', 'consent': True,
    })
    experience_id = captured.json()['experience']['id']
    client.post(f'/api/experiences/{experience_id}/verify', headers=alice,
                json={'method': 'outcome_signal', 'evidence_confirmed': True})

    invite = client.post(f'/api/orgs/{org_id}/invites', headers=alice, json={'ttl_hours': 24, 'max_uses': 2})
    assert invite.status_code == 201, invite.text
    code = invite.json()['invite']['code']

    carol = signed_in(client, 'carol@acme.example', 'Carol')
    joined = client.post('/api/orgs/join', headers=carol, json={'code': code})
    assert joined.status_code == 200, joined.text
    assert joined.json()['organization']['id'] == org_id
    carol = bearer(joined.json()['access_token'])

    # The whole point: a teammate's AI reaches the lesson it did not pay for.
    carol_recall = client.post('/api/recall', headers=carol, json={'query': 'cache the CI container layers'})
    assert [r['experience_id'] for r in carol_recall.json()['receipts']] == [experience_id], carol_recall.text
    assert carol_recall.json()['receipts'][0]['actor'] == 'Alice', carol_recall.text

    members = client.get(f'/api/orgs/{org_id}/members', headers=carol)
    assert members.status_code == 200, members.text
    by_email = {m['email']: m for m in members.json()['members']}
    assert by_email['alice@acme.example']['experiences_contributed'] == 1, members.text
    assert by_email['alice@acme.example']['verified_contributions'] == 1, members.text
    assert by_email['alice@acme.example']['times_reused_by_others'] >= 1, members.text
    assert by_email['carol@acme.example']['experiences_contributed'] == 0, members.text
    assert members.json()['totals']['members'] == 2, members.text

    # A non-admin may not mint invites, and a revoked code stops admitting people.
    assert client.post(f'/api/orgs/{org_id}/invites', headers=carol, json={}).status_code == 403
    assert client.delete(f'/api/orgs/{org_id}/invites/{code}', headers=alice).status_code == 200
    dave = signed_in(client, 'dave@nowhere.example', 'Dave')
    refused = client.post('/api/orgs/join', headers=dave, json={'code': code})
    assert refused.status_code == 422, refused.text
print('invite and contribution counts: OK')
'''
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = run_script(script, temporary_directory)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn('invite and contribution counts: OK', result.stdout)

    def test_signed_in_without_an_organization_is_served_nothing(self) -> None:
        """Fail closed: no organization means no memory, not somebody else's memory."""
        script = PRELUDE + r'''
with TestClient(app) as client:
    alice = signed_in(client, 'alice@acme.example', 'Alice')
    acme = client.post('/api/orgs', headers=alice, json={'name': 'Acme Research'})
    alice_scoped = bearer(acme.json()['access_token'])
    client.post('/api/capture', headers=alice_scoped, json={
        'task': 'Rotate the signing key', 'trace_summary': 'The rotation completed cleanly.',
        'tool_name': 'Codex', 'tags': ['security'], 'visibility': 'team', 'consent': True,
    })

    homeless = signed_in(client, 'dave@nowhere.example', 'Dave')
    for path, method, body in (
        ('/api/recall', 'post', {'query': 'rotate the signing key'}),
        ('/api/experiences', 'get', None),
        ('/api/dashboard/team', 'get', None),
        ('/api/auth/connections', 'get', None),
    ):
        response = client.request(method.upper(), path, headers=homeless, json=body)
        assert response.status_code == 409, f'{path} returned {response.status_code}: {response.text}'
    assert client.get('/api/orgs', headers=homeless).json()['organizations'] == []
print('no organization means no memory: OK')
'''
        with tempfile.TemporaryDirectory() as temporary_directory:
            result = run_script(script, temporary_directory)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn('no organization means no memory: OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
