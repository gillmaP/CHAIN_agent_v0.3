"""HTTP Site Data API connector and explicit Mock-v0.12 presentation adapter."""
import copy
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


def _combine_history(items):
    """Three-valued OR; do not turn unknown surgery/bleeding into a negative."""
    selected = [items[q] for q in ('recent_surgery', 'recent_bleeding') if q in items]
    evidence = [e for x in selected for e in x['evidence']]
    if any(x['status'] == 'documented' and x['value'] is True for x in selected):
        return {'status': 'documented', 'value': True, 'evidence': evidence, 'alternatives': []}
    if len(selected) == 2 and all(x['status'] == 'documented' and x['value'] is False for x in selected):
        return {'status': 'documented', 'value': False, 'evidence': evidence, 'alternatives': []}
    return {'status': 'explicitly_unknown', 'value': None, 'evidence': evidence, 'alternatives': []}


def mock_output(domain, request, execution_id, produced_time, processing_time_ms):
    """Shape-compatible integration profile, NOT the unchanged clinical v0.1 schema.

    Typed fields remain in typed_items. Confidence is deliberately null. No claim of
    Safety Gate approval or physician confirmation is made.
    """
    typed = {x['question']: copy.deepcopy(x) for x in domain['items']}
    fields = dict(typed)
    if 'recent_surgery_or_bleeding' in request['questions']:
        fields['recent_surgery_or_bleeding'] = _combine_history(typed)
        fields.pop('recent_surgery', None)
        fields.pop('recent_bleeding', None)
    items = {}
    for q, item in fields.items():
        status, value = item['status'], item['value']
        if status == 'documented':
            if q == 'lkw_records':
                status = 'RECORDED'
                if value['kind'] == 'point':
                    value = value['start']
            else:
                status = 'PRESENT' if value else 'NO_EVIDENCE'
                if q == 'previous_stroke' and value is False:
                    status = 'NONE_DOCUMENTED'
        else:
            status = {'not_stated': 'NOT_STATED', 'explicitly_unknown': 'UNKNOWN',
                      'conflicting': 'CONFLICTING', 'not_applicable': 'NOT_APPLICABLE'}[status]
        items[q] = {'status': status, 'value': value, 'confidence': None,
                    'sources': copy.deepcopy(item['evidence']),
                    'confirmation_status': 'UNCONFIRMED',
                    'alternatives': copy.deepcopy(item['alternatives'])}
    return {
        'schema_version': 'clinical-summary-integration/v1',
        'agent_id': 'clinical-summary-agent', 'agent_version': '0.3.0-prototype',
        'execution_id': execution_id, 'episode_id': domain['episode_id'],
        'encounter_id': domain['encounter_id'], 'items': items,
        'missing_information': copy.deepcopy(domain['missing_information']),
        'produced_time': produced_time, 'processing_time_ms': processing_time_ms,
        'model_info': copy.deepcopy(domain['model_info']), 'mock_only': domain['mock_only'],
        'typed_schema_version': domain['schema_version'], 'typed_items': copy.deepcopy(domain['items']),
        'compatibility_notes': [
            'Mock v0.12 routes and object-shaped items; integration/v1 is an explicit extension, not an approved v0.1 schema.',
            'confidence=null is uncalibrated; all confirmation states remain UNCONFIRMED.',
            'Antiplatelet value remains boolean; medication details are in sources/typed_items.',
            'Unknown/conflicting/approximate times are preserved; no invented negative or exact time.',
        ],
    }
