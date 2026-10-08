"""Scoped Site Data API access adapter supplied to Team 1 by JLK Runtime.

No HTTP listener: this is a *client* for the reference-only v0.12 input.
The token/URL are configuration injected by an authorized runtime, never from
LLM output or the event body. Offline fixture client is synthetic-data only.
"""
from __future__ import annotations
import copy
import json
import re
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpSiteDataAPI:
    """Fetch only whitelisted Screening v0.12 paths using runtime authorization."""
    def __init__(self, base_url: str, *, bearer_token: str | None = None,
                 allow_mock_localhost: bool = False, timeout_s: int = 10):
        parsed = urlsplit(base_url)
        if parsed.scheme not in ('https', 'http') or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError('Invalid trusted Site Data API base URL')
        mock = parsed.hostname in {'localhost','127.0.0.1','::1'} and allow_mock_localhost
        if parsed.scheme != 'https' and not mock:
            raise ValueError('Site Data API requires HTTPS except explicitly opted-in localhost mock')
        if not mock and not bearer_token:
            raise ValueError('WG4 authorized execution bearer token is required for non-mock Site Data API')
        self.base_url = base_url.rstrip('/')
        self.token = bearer_token
        self.timeout_s = timeout_s
        self.opener = build_opener(_NoRedirect())

    def get(self, path: str) -> dict:
        # Do not allow arbitrary child endpoints such as current/future
        # observations. The scoped context must come from the authorized
        # as-of-trigger request, not a later API snapshot.
        document_path = re.fullmatch(r'/documents/[A-Za-z0-9_-]+\?version=[1-9][0-9]*', path)
        encounter_path = re.fullmatch(r'/encounters/[A-Za-z0-9_-]+', path)
        if not (document_path or encounter_path):
            raise ValueError('Endpoint not in Stroke Screening read scope')
        if '://' in path or '..' in path or '#' in path:
            raise ValueError('Invalid data reference')
        url = self.base_url + path
        headers = {'Accept': 'application/json'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        with self.opener.open(Request(url, headers=headers), timeout=self.timeout_s) as response:
            if response.status != 200:
                raise RuntimeError('Site Data API refused request')
            return json.loads(response.read(1024*1024).decode('utf-8'))


class SyntheticFixtureDataAPI:
    """Read-only lookup from selected mock_v0.12/files/15_data_api_simple.json keys."""
    def __init__(self, fixtures: dict):
        if not isinstance(fixtures, dict):
            raise ValueError('Fixture data must be a dict')
        self.fixtures = copy.deepcopy(fixtures)

    def get(self, path: str) -> dict:
        key = 'GET ' + path
        if key not in self.fixtures:
            raise KeyError('Requested path not present in scoped synthetic fixture')
        return copy.deepcopy(self.fixtures[key])
