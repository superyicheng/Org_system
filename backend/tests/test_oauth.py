import base64
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sqlalchemy import create_engine

from app.oauth import OAuthError, OAuthStore, pkce_matches


def challenge_for(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode('ascii')).digest()).rstrip(b'=').decode('ascii')


class PkceAndGrantTest(unittest.TestCase):
    """The authorization server's security properties, without any HTTP in the way."""

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.directory.name) / 'oauth.sqlite3'}")
        self.store = OAuthStore(self.engine)
        self.client = self.store.register_client(client_name='Test client', redirect_uris=['http://127.0.0.1:8765/callback'])

    def tearDown(self) -> None:
        self.engine.dispose()
        self.directory.cleanup()

    def issue(self, verifier: str = 'a' * 64) -> str:
        return self.store.issue_code(
            client_id=self.client['client_id'], redirect_uri='http://127.0.0.1:8765/callback',
            code_challenge=challenge_for(verifier), email='sarah@acme.example', org_id='org-acme', scope='org.read',
        )

    def consume(self, code: str, **overrides: str) -> dict[str, str]:
        arguments = {
            'code': code, 'client_id': self.client['client_id'],
            'redirect_uri': 'http://127.0.0.1:8765/callback', 'verifier': 'a' * 64,
        }
        arguments.update(overrides)
        return self.store.consume_code(**arguments)

    def test_pkce_helper_only_accepts_the_matching_verifier(self) -> None:
        self.assertTrue(pkce_matches('a' * 64, challenge_for('a' * 64)))
        self.assertFalse(pkce_matches('b' * 64, challenge_for('a' * 64)))

    def test_wrong_verifier_is_rejected(self) -> None:
        code = self.issue()
        with self.assertRaises(OAuthError) as caught:
            self.consume(code, verifier='b' * 64)
        self.assertEqual(caught.exception.code, 'invalid_grant')

    def test_redirect_uri_must_match_the_authorization_request(self) -> None:
        code = self.issue()
        with self.assertRaises(OAuthError):
            self.consume(code, redirect_uri='http://127.0.0.1:8765/somewhere-else')

    def test_replaying_a_code_revokes_the_tokens_it_already_minted(self) -> None:
        """A second use means the code leaked, so the first client's tokens must die."""
        code = self.issue()
        granted = self.consume(code)
        tokens = self.store.issue_tokens(client_id=self.client['client_id'], **granted)
        self.assertIsNotNone(self.store.identity_for_access_token(tokens['access_token']))

        with self.assertRaises(OAuthError):
            self.consume(code)
        self.assertIsNone(
            self.store.identity_for_access_token(tokens['access_token']),
            'tokens minted from a replayed code must be revoked',
        )

    def test_refresh_rotates_and_retires_the_old_token(self) -> None:
        granted = self.consume(self.issue())
        first = self.store.issue_tokens(client_id=self.client['client_id'], **granted)
        second = self.store.rotate_refresh_token(refresh_token=first['refresh_token'], client_id=self.client['client_id'])
        self.assertNotEqual(first['refresh_token'], second['refresh_token'])
        with self.assertRaises(OAuthError):
            self.store.rotate_refresh_token(refresh_token=first['refresh_token'], client_id=self.client['client_id'])

    def test_token_carries_its_organization_and_can_be_revoked(self) -> None:
        granted = self.consume(self.issue())
        tokens = self.store.issue_tokens(client_id=self.client['client_id'], **granted)
        identity = self.store.identity_for_access_token(tokens['access_token'])
        self.assertEqual(identity.org_id, 'org-acme')
        self.assertEqual(identity.email, 'sarah@acme.example')

        connections = self.store.connections(email='sarah@acme.example')
        self.assertEqual(len(connections), 1)
        self.assertTrue(self.store.revoke_connection(connection_id=connections[0]['id'], email='sarah@acme.example'))
        self.assertIsNone(self.store.identity_for_access_token(tokens['access_token']))

    def test_loopback_http_is_allowed_but_public_http_is_not(self) -> None:
        self.store.register_client(client_name='Local', redirect_uris=['http://localhost:1234/cb'])
        with self.assertRaises(OAuthError):
            self.store.register_client(client_name='Insecure', redirect_uris=['http://example.com/cb'])


class DiscoveryAndEndToEndTest(unittest.TestCase):
    def test_client_can_discover_authorize_and_call_mcp(self) -> None:
        """The whole point: no pasted token anywhere in this flow."""
        script = r'''
import base64, hashlib, json
from fastapi.testclient import TestClient
from app.main import app

verifier = 'v' * 64
challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()

with TestClient(app) as client:
    # 1. The 401 challenge must point at a document that actually exists.
    unauthorized = client.post('/mcp/', headers={'Accept': 'application/json, text/event-stream',
                                                'Content-Type': 'application/json'},
                               json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {}})
    assert unauthorized.status_code == 401, unauthorized.text
    challenge_header = unauthorized.headers.get('www-authenticate', '')
    assert 'resource_metadata=' in challenge_header, challenge_header
    advertised = challenge_header.split('resource_metadata="')[1].split('"')[0]
    path = advertised.replace('http://testserver', '')
    resolved = client.get(path)
    assert resolved.status_code == 200, f'advertised metadata {path} returned {resolved.status_code}'
    assert resolved.json()['authorization_servers'], resolved.text

    # 2. RFC 9728 canonical location works too.
    canonical = client.get('/.well-known/oauth-protected-resource/mcp')
    assert canonical.status_code == 200, canonical.text

    # 3. Authorization server metadata advertises PKCE and dynamic registration.
    meta = client.get('/.well-known/oauth-authorization-server').json()
    assert meta['code_challenge_methods_supported'] == ['S256'], meta
    assert meta['registration_endpoint'].endswith('/oauth/register'), meta

    # 4. Dynamic client registration, with no pre-shared configuration.
    registered = client.post('/oauth/register', json={
        'client_name': 'Claude Code', 'redirect_uris': ['http://127.0.0.1:33418/callback'],
        'grant_types': ['authorization_code', 'refresh_token'], 'unknown_field': 'ignored',
    })
    assert registered.status_code == 201, registered.text
    client_id = registered.json()['client_id']

    # 5. The consent page renders and does not leak a code before consent.
    page = client.get('/oauth/authorize', params={
        'response_type': 'code', 'client_id': client_id, 'redirect_uri': 'http://127.0.0.1:33418/callback',
        'code_challenge': challenge, 'code_challenge_method': 'S256', 'state': 'xyz',
    })
    assert page.status_code == 200, page.text
    assert 'ocode_' not in page.text

    # An unregistered redirect target must be refused, not redirected to.
    hostile = client.get('/oauth/authorize', params={
        'response_type': 'code', 'client_id': client_id, 'redirect_uri': 'http://evil.example/steal',
        'code_challenge': challenge, 'code_challenge_method': 'S256',
    })
    assert hostile.status_code == 200 and 'did not register' in hostile.text, hostile.text

    # 6. Consent: first call reports the organizations, second returns the redirect.
    consent_body = {'client_id': client_id, 'redirect_uri': 'http://127.0.0.1:33418/callback',
                    'code_challenge': challenge, 'state': 'xyz', 'scope': 'org.read org.write'}
    stage_one = client.post('/oauth/authorize/consent', json=consent_body)
    assert stage_one.status_code == 200, stage_one.text
    assert stage_one.json()['stage'] == 'choose_organization', stage_one.text
    org_id = stage_one.json()['organizations'][0]['id']

    granted = client.post('/oauth/authorize/consent', json={**consent_body, 'org_id': org_id})
    assert granted.status_code == 200, granted.text
    location = granted.json()['redirect_to']
    assert 'state=xyz' in location, location
    code = location.split('code=')[1].split('&')[0]

    # 7. Token exchange, form encoded exactly as an MCP client sends it.
    wrong = client.post('/oauth/token', data={'grant_type': 'authorization_code', 'code': code,
                                              'client_id': client_id, 'code_verifier': 'w' * 64,
                                              'redirect_uri': 'http://127.0.0.1:33418/callback'})
    assert wrong.status_code == 400 and wrong.json()['error'] == 'invalid_grant', wrong.text

    # That failed attempt consumed the code, so run the flow again for the happy path.
    granted = client.post('/oauth/authorize/consent', json={**consent_body, 'org_id': org_id})
    code = granted.json()['redirect_to'].split('code=')[1].split('&')[0]
    exchanged = client.post('/oauth/token', data={'grant_type': 'authorization_code', 'code': code,
                                                  'client_id': client_id, 'code_verifier': verifier,
                                                  'redirect_uri': 'http://127.0.0.1:33418/callback'})
    assert exchanged.status_code == 200, exchanged.text
    tokens = exchanged.json()
    assert tokens['token_type'] == 'Bearer' and tokens['refresh_token'], tokens

    # 8. The access token works on the MCP endpoint and on the REST API.
    mcp_headers = {'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json',
                   'Authorization': 'Bearer ' + tokens['access_token']}
    initialized = client.post('/mcp/', headers=mcp_headers, json={
        'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
        'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 't', 'version': '1'}}})
    assert initialized.status_code == 200, initialized.text
    me = client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + tokens['access_token']})
    assert me.status_code == 200, me.text

    # 9. Refresh works, and revocation actually stops the token.
    refreshed = client.post('/oauth/token', data={'grant_type': 'refresh_token', 'client_id': client_id,
                                                  'refresh_token': tokens['refresh_token']})
    assert refreshed.status_code == 200, refreshed.text
    revoked = client.post('/oauth/revoke', data={'token': refreshed.json()['access_token']})
    assert revoked.status_code == 200, revoked.text
    dead = client.post('/mcp/', headers={**mcp_headers, 'Authorization': 'Bearer ' + refreshed.json()['access_token']},
                       json={'jsonrpc': '2.0', 'id': 2, 'method': 'initialize', 'params': {}})
    assert dead.status_code == 401, dead.text
print('oauth end to end: OK')
'''
        with tempfile.TemporaryDirectory() as temporary_directory:
            environment = os.environ.copy()
            environment.update({
                'AUTH_MODE': 'demo',
                'PUBLIC_URL': 'http://testserver',
                'ALLOWED_ORIGINS': 'http://testserver',
                'DATABASE_URL': f"sqlite:///{Path(temporary_directory) / 'oauth-e2e.sqlite3'}",
                'ORG_SYSTEM_LLM_MODE': 'mock',
            })
            result = subprocess.run(
                [sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                env=environment, capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn('oauth end to end: OK', result.stdout)


if __name__ == '__main__':
    unittest.main()
