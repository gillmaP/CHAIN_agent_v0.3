"""Read-only Site Data API client injected by Runtime; no HTTP listener."""
import json
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DataAPIError(RuntimeError):
    pass


class HTTPDataAPI:
    """Paths originate only in mock_contract.endpoint; credentials never enter LLM input."""
    def __init__(self, base_url, token=None, timeout=15, mock_only=False):
        url = urllib.parse.urlsplit(base_url)
        if url.scheme not in ('http', 'https') or not url.netloc or url.username or url.password or url.query or url.fragment:
            raise ValueError('Data API base must be an http(s) URL without credentials/query/fragment')
        self.base_url = base_url.rstrip('/')
        self.token, self.timeout, self.mock_only = token, timeout, mock_only
        self.opener = urllib.request.build_opener(NoRedirect())
        self.accessed = []

    def get(self, path):
        parsed = urllib.parse.urlsplit(path)
        if parsed.scheme or parsed.netloc or not path.startswith('/') or '..' in parsed.path.split('/'):
            raise ValueError('Only relative Site Data API paths are allowed')
        headers = {'Accept': 'application/json'}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        try:
            with self.opener.open(urllib.request.Request(self.base_url + path, headers=headers), timeout=self.timeout) as response:
                if response.headers.get('X-CHAIN-Mock', '').lower() == 'true':
                    self.mock_only = True
                raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise DataAPIError('Data API response exceeds 8 MiB')
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise DataAPIError('Data API response must be an object')
        except (urllib.error.URLError, OSError, ValueError) as exc:
            # Do not return upstream response bodies or credentials to callers.
            raise DataAPIError('Site Data API read failed') from exc
        self.accessed.append(path)
        return result


