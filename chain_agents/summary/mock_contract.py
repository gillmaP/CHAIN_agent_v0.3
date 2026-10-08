"""Clinical Summary domain contract for reference-based mock v0.12 requests."""
import copy
import re
from urllib.parse import quote

QUESTIONS = ('anticoagulant_use', 'recent_surgery_or_bleeding', 'previous_stroke', 'lkw_records')
ITEMS = QUESTIONS + ('antiplatelet_use', 'recent_surgery', 'recent_bleeding')
DOCUMENT_TYPES = {'ED_INITIAL_NOTE', 'ED_TRIAGE_NOTE'}

def requested_items(request):
    if not isinstance(request, dict):
        raise ValueError('Summary request must be an object')
    for key in ('episode_id', 'encounter_id', 'patient_id'):
        if not isinstance(request.get(key), str) or not request[key].strip():
            raise ValueError(f'{key} required')
    qs = request.get('questions')
    if not isinstance(qs, list) or not qs or any(q not in ITEMS for q in qs):
        raise ValueError('Unsupported or empty Summary questions')
    refs = request.get('input_references')
    if not isinstance(refs, list) or not refs or any(not isinstance(x,str) for x in refs) or len(set(refs)) != len(refs):
        raise ValueError('Unique input_references required')
    items = list(dict.fromkeys(qs))
    # v0.12 purpose/output includes antiplatelets alongside anticoagulants.
    if 'anticoagulant_use' in items and 'antiplatelet_use' not in items: items.append('antiplatelet_use')
    return items

def endpoint(ref, request):
    pid = quote(request['patient_id'], safe='')
    paths = {'medication:active':f'/patients/{pid}/medications?status=active',
             'condition:problem_list':f'/patients/{pid}/conditions',
             'encounter_history:6m':f'/patients/{pid}/encounters?months=6'}
    if ref in paths: return paths[ref]
    match = re.fullmatch(r'document:([A-Za-z0-9_-]+)@([1-9][0-9]*)',ref)
    if not match: raise ValueError(f'Unsupported Summary reference: {ref}')
    return f'/documents/{match[1]}?version={match[2]}'

class FixtureDataAPI:
    """Reads Site Data API JSON responses, never canned agent outputs."""
    mock_only = True
    def __init__(self, responses): self.responses = copy.deepcopy(responses)
    def get(self, path):
        key='GET '+path
        if key not in self.responses: raise ValueError(f'Missing API fixture: {key}')
        return copy.deepcopy(self.responses[key])

def resolve(request, reader, audit=None):
    requested_items(request)
    if reader is None or not callable(getattr(reader,'get',None)):
        raise ValueError('services.summary_data_api.get(path) required')
    resources={}
    for ref in request['input_references']:
        from .input_audit import InputResolutionError, now
        started = now()
        stage = 'retrieve'
        try:
            resource=copy.deepcopy(reader.get(endpoint(ref,request)))
            stage = 'validate'
            if not isinstance(resource,dict): raise ValueError(f'Invalid resource: {ref}')
            if resource.get('patient_id') != request['patient_id']: raise ValueError(f'Patient binding mismatch: {ref}')
            if ref.startswith('document:'):
                docid,version=ref[9:].split('@')
                if resource.get('document_id')!=docid or resource.get('version')!=int(version): raise ValueError('Document version mismatch')
                if resource.get('encounter_id')!=request['encounter_id']: raise ValueError('Document encounter mismatch')
                if resource.get('document_type') not in DOCUMENT_TYPES: raise ValueError('Document outside Summary scope')
                if resource.get('status') not in ('CURRENT','SUPERSEDED') or not isinstance(resource.get('text'),str): raise ValueError('Invalid/retracted document')
            if audit is not None:
                audit.record(ref, resource, started)
        except Exception as exc:
            if audit is not None:
                audit.failed(ref, stage)
            raise InputResolutionError(f'Required source {stage} failed: {ref}') from exc
        resources[ref]=resource
    return resources
