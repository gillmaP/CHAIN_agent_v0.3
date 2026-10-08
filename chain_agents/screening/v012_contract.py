"""Mock v0.12 stroke Screening adapter (Team 1 only).

The JLK Agent Runtime calls ``invoke_v012`` and receives a Python dict; writing a
JSON file is *not* part of the orchestration protocol. The runtime is responsible
for Safety Gate authorization, the execution token, persistence, hash/event
publication and S0->S1 transition. This module does not provide an HTTP server.

The upstream v0.12 zip provides a sample, NOT the referenced JSON Schema file.
The keys below follow files/05_agent_executions.json, execution[0].input/output.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import hashlib
import re
from time import perf_counter
from typing import Any
from urllib.parse import quote

from .prototype import screen_documents, ScreeningResponseError

AGENT_ID = 'stroke-screening-agent'
AGENT_VERSION = '0.3.0'
ALLOWED_DOCUMENT_TYPES = frozenset({'ED_INITIAL_NOTE', 'ED_TRIAGE_NOTE'})
ALLOWED_CONTEXT_REFS = frozenset({
    'observation:vital_signs', 'observation:poct_glucose', 'condition:problem_list'
})
INPUT_FIELDS = frozenset({
    'episode_id', 'encounter_id', 'patient_id', 'trigger_event_id',
    'input_references', 'documents', 'structured_context',
})
OUTPUT_FIELDS = frozenset({
    'agent_id', 'agent_version', 'execution_id', 'episode_id', 'encounter_id',
    'result', 'confidence', 'rule_trace', 'text_derived_findings',
    'clinical_times', 'missing_information', 'evidence', 'produced_time',
    'processing_time_ms', 'model_info', 'disclaimer',
})


class V012ContractError(ValueError):
    """Malformed or out-of-scope input or unverified model result; fail closed."""


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise V012ContractError(f'{name} must be a nonempty string')
    return value


def _document_reference(ref: str) -> tuple[str, int]:
    match = re.fullmatch(r'document:([A-Za-z0-9_-]+)@(\d+)', ref)
    if not match or int(match.group(2)) < 1:
        raise V012ContractError('Invalid document:ID@version reference')
    return match.group(1), int(match.group(2))


def validate_v012_input(payload: dict) -> dict:
    if not isinstance(payload, dict) or set(payload) != INPUT_FIELDS:
        raise V012ContractError('v0.12 input must have exactly the 7 documented top-level keys')
    for key in ('episode_id', 'encounter_id', 'patient_id', 'trigger_event_id'):
        _nonempty(payload[key], key)
    refs = payload['input_references']
    if not isinstance(refs, list) or not refs or len(refs) != len(set(refs)) or not all(isinstance(r, str) for r in refs):
        raise V012ContractError('input_references must be a unique string list')
    declared_docs = payload['documents']
    if not isinstance(declared_docs, list) or not (1 <= len(declared_docs) <= 2):
        raise V012ContractError('Expect ED_INITIAL_NOTE and optional ED_TRIAGE_NOTE')
    context = payload['structured_context']
    if not isinstance(context, dict):
        raise V012ContractError('structured_context must be an object')
    # These are the fields in the v0.12 Screening reference case. Missing values
    # are allowed, since real clinical records can be incomplete; unknown fields
    # (including names/local identifiers) are not allowed through this boundary.
    context_fields = {'age', 'sex', 'arrival_time', 'arrival_mode',
                      'triage_level', 'vital_signs', 'poct_glucose_mg_dl',
                      'problem_list', 'seizure_history', 'preexisting_hemiparesis'}
    if set(context) - context_fields:
        raise V012ContractError('Unknown or out-of-scope structured_context field')
    if 'age' in context and (type(context['age']) is not int or not 0 <= context['age'] <= 120):
        raise V012ContractError('Invalid age')
    if 'poct_glucose_mg_dl' in context and (type(context['poct_glucose_mg_dl']) not in (int, float)
                                             or not 0 <= context['poct_glucose_mg_dl'] <= 2000):
        raise V012ContractError('Invalid POCT glucose')
    if 'problem_list' in context and (not isinstance(context['problem_list'], list)
                                     or not all(isinstance(x, str) for x in context['problem_list'])):
        raise V012ContractError('Invalid problem_list')
    if 'vital_signs' in context:
        vitals = context['vital_signs']
        allowed_vitals = {'sbp', 'dbp', 'hr', 'rr', 'bt', 'spo2', 'measured_time'}
        if not isinstance(vitals, dict) or set(vitals) - allowed_vitals:
            raise V012ContractError('Invalid vital_signs')
    for key in ('arrival_time',):
        if key in context:
            try:
                time = datetime.fromisoformat(context[key])
                if time.tzinfo is None: raise ValueError()
            except (ValueError, TypeError):
                raise V012ContractError('Invalid timezone-aware arrival_time')

    doc_refs = [r for r in refs if r.startswith('document:')]
    if len(doc_refs) != len(declared_docs):
        raise V012ContractError('Document reference count does not match documents metadata')
    if not any(r.startswith('document:') for r in refs):
        raise V012ContractError('Missing document reference')
    seen = set()
    saw_initial = False
    for item in declared_docs:
        if not isinstance(item, dict) or set(item) != {'document_id', 'version', 'document_type', 'text_hash'}:
            raise V012ContractError('Document metadata must have exactly 4 v0.12 keys')
        name = _nonempty(item['document_id'], 'document_id')
        if type(item['version']) is not int or item['version'] < 1:
            raise V012ContractError('Document version must be positive integer')
        kind = item['document_type']
        if kind not in ALLOWED_DOCUMENT_TYPES:
            raise V012ContractError('Document type outside Screening manifest')
        if kind == 'ED_INITIAL_NOTE':
            saw_initial = True
        sha = _nonempty(item['text_hash'], 'text_hash')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', sha):
            raise V012ContractError('Invalid document text_hash')
        ref = f"document:{name}@{item['version']}"
        if ref not in doc_refs or ref in seen:
            raise V012ContractError('Document metadata does not match scoped input_references')
        seen.add(ref)
    if not saw_initial:
        raise V012ContractError('v0.12 Screening needs ED_INITIAL_NOTE')
    allowed = seen | {f"encounter:{payload['encounter_id']}"} | ALLOWED_CONTEXT_REFS
    if set(refs) - allowed:
        raise V012ContractError('Out-of-scope or mismatched input reference')
    if f"encounter:{payload['encounter_id']}" not in refs:
        raise V012ContractError('Missing encounter reference')
    return copy.deepcopy(payload)


def _fetch_scoped_documents(payload: dict, data_api: Any) -> list[dict]:
    """data_api.get(relative_path) is provided by authorized Site Runtime."""
    docs = []
    for item in payload['documents']:
        ref = f"document:{item['document_id']}@{item['version']}"
        if ref not in payload['input_references']:
            raise V012ContractError('Missing authorized document reference')
        path = f"/documents/{quote(item['document_id'], safe='')}?version={item['version']}"
        fetched = data_api.get(path)
        if not isinstance(fetched, dict):
            raise V012ContractError('Site Data API document response must be an object')
        for key in ('document_id', 'version', 'document_type', 'encounter_id', 'patient_id'):
            expected = item[key] if key in item else payload[key]
            if fetched.get(key) != expected:
                raise V012ContractError(f'Document {key} differs from authorized reference')
        text = fetched.get('text')
        if not isinstance(text, str) or not text.strip():
            raise V012ContractError('Site Data API document text unavailable')
        sha = 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()
        if sha != item['text_hash'] or fetched.get('text_hash') != sha:
            raise V012ContractError('Document SHA-256 does not match authorized input')
        docs.append({
            'document_id': item['document_id'], 'version': item['version'],
            'document_type': item['document_type'], 'saved_time': fetched.get('saved_time'),
            'text': text,
        })
    return docs


def _validate_context_scope(payload: dict, data_api: Any) -> None:
    """Check encounter identity and referenced structured data access scopes.

    Structured context values supplied by Orchestrator are NOT overwritten with
    current-day Site Data API values: the v0.12 test is timestamped at 15:19:52.
    """
    encounter = data_api.get('/encounters/' + quote(payload['encounter_id'], safe=''))
    if not isinstance(encounter, dict) or encounter.get('encounter_id') != payload['encounter_id'] or encounter.get('patient_id') != payload['patient_id']:
        raise V012ContractError('Encounter identity mismatch')
    # Other context is supplied by the already-authorized Runner at trigger time.
    # Do not fetch the latest observation/problem-list here, since the fixture API
    # is a later snapshot (it includes values not available when Screening ran).
    # The Runtime must attest that structured_context is an as-of-trigger snapshot.



def _iso_time_from_quote(quote_text: str, base: str) -> str | None:
    """Conservatively normalize an explicit clock-time in cited text only."""
    match = re.search(r'(?<!\d)(\d{1,2}):(\d{2})(?!\d)', quote_text)
    if not match:
        match = re.search(r'(?<!\d)(\d{1,2})시\s*(\d{1,2})분', quote_text)
    if not match:
        return None
    hour, minute = map(int, match.groups())
    if hour > 23 or minute > 59:
        return None
    try:
        dt = datetime.fromisoformat(base)
        if dt.tzinfo is None:
            return None
        return dt.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat(timespec='seconds')
    except (ValueError, TypeError):
        return None


def _clinical_times(findings: list[dict], structured: dict, docs: list[dict]) -> dict:
    base = structured.get('arrival_time')
    result = {'last_known_well': None, 'symptom_discovery': None,
              'ems_arrival': None, 'source_ref': None,
              'confirmation_status': 'UNCONFIRMED_NLP_EXTRACTED'}
    if not isinstance(base, str):
        return result
    for finding in findings:
        if finding['status'] != 'present':
            continue
        name = {'lkw': 'last_known_well', 'symptom_discovery': 'symptom_discovery'}.get(finding['code'])
        if name and result[name] is None:
            value = _iso_time_from_quote(finding['quote'], base)
            if value:
                result[name] = value
                result['source_ref'] = finding['source_ref']
    # Only extract explicit EMS arrival, never infer it from the encounter time.
    for doc in docs:
        match = re.search(r'(?:구급대\s*도착|119\s*도착|EMS\s*arrival)[^\n]{0,35}', doc['text'], re.I)
        if match:
            t = _iso_time_from_quote(match.group(), base)
            if t:
                result['ems_arrival'] = t
                break
    return result


def _confidence_evidence_coverage(findings: list[dict], screening: str) -> float:
    """Nonclinical *coverage score*, NOT model probability; JLK must approve semantics."""
    if not findings:
        return 0.0
    present = {f['code'] for f in findings if f['status'] == 'present'}
    valid_alt = any(f['code'] in {'seizure', 'trauma', 'hypoglycemia'} and f['status'] == 'absent' for f in findings)
    evidence_source_count = len({f['source_ref'] for f in findings})
    coverage = .2 + .25*('acute_onset' in present) + .25*(bool(present & {
        'focal_weakness', 'facial_droop', 'language_or_speech_deficit',
        'vision_deficit', 'gait_or_coordination_deficit', 'fast_positive'}))
    coverage += .1 * valid_alt + .1 * ('lkw' in present) + .1 * (evidence_source_count >= 2)
    return round(min(1.0, coverage), 2)


def to_v012_output(payload: dict, execution_id: str, prototype: dict,
                   docs: list[dict], *, processing_time_ms: int, produced_time: str) -> dict:
    """Convert only verified findings to sample v0.12 output shape."""
    screening = prototype['screening_result']
    if screening not in {'POSITIVE', 'NEGATIVE'}:
        raise V012ContractError('Uncertain Screening result: fail closed without S1 transition')
    findings = prototype['evidence']
    if screening == 'POSITIVE' and not any(f['status'] == 'present' for f in findings):
        raise V012ContractError('POSITIVE result has no supporting document evidence')
    neg_alt = any(f['code'] in {'hypoglycemia', 'seizure', 'trauma'} and f['status'] == 'present' for f in findings)
    trace = []
    for rule in prototype['rule_trace']:
        if rule['rule'] == 'R3_NO_CONTRADICTION':
            satisfied = bool(rule['satisfied']) and not neg_alt
            basis = ('Strong alternative documented; clinical review required' if neg_alt else
                     'No conflicting evidence identified; unknown alternatives are not ruled out')
            trace.append({'rule': 'R3_NO_STRONG_ALTERNATIVE', 'satisfied': satisfied, 'basis': basis})
        else:
            trace.append({'rule': rule['rule'], 'satisfied': bool(rule['satisfied']), 'basis': str(rule['basis'])})
    if neg_alt and screening == 'POSITIVE':
        raise V012ContractError('Documented alternative etiology requires clinical review')
    labels = {
        'acute_onset': '급성 발생', 'focal_weakness': '국소 근력 저하',
        'language_or_speech_deficit': '언어/구음장애', 'facial_droop': '안면마비',
        'vision_deficit': '시야장애', 'gait_or_coordination_deficit': '보행/협응장애',
        'fast_positive': 'FAST 양성', 'no_focal_deficit': '국소 신경학적 결손 부재',
        'lkw': '마지막 정상 확인 시각', 'symptom_discovery': '증상 발견 시각',
        'seizure': '경련', 'trauma': '외상', 'hypoglycemia': '저혈당',
    }
    text_findings = [
        {'finding': f['code'], 'label': labels[f['code']], 'snomed': None,
         'source_ref': f['source_ref'], 'quote': f['quote']}
        for f in findings
    ]
    evidence = [{'source_ref': f['source_ref'], 'quote': f['quote'], 'finding': f['code']}
                for f in findings]
    model_info = prototype['model_info']
    output = {
        'agent_id': AGENT_ID,
        'agent_version': AGENT_VERSION,
        'execution_id': _nonempty(execution_id, 'execution_id'),
        'episode_id': payload['episode_id'], 'encounter_id': payload['encounter_id'],
        'result': {'screening_result': screening,
                   'proposed_state': 'S1' if screening == 'POSITIVE' else 'S0X',
                   'clinical_label': 'SUSPECTED_ACUTE_STROKE' if screening == 'POSITIVE' else 'SCREEN_NEGATIVE',
                   'priority': 'HIGH' if screening == 'POSITIVE' else 'NONE'},
        'confidence': _confidence_evidence_coverage(findings, screening),
        'rule_trace': trace,
        'text_derived_findings': text_findings,
        'clinical_times': _clinical_times(findings, payload['structured_context'], docs),
        'missing_information': list(prototype['missing_information']),
        'evidence': evidence,
        'produced_time': produced_time,
        'processing_time_ms': processing_time_ms,
        'model_info': {'rule_set': 'screening-evidence-prototype v0.1',
                       'nlp_model': str(model_info.get('model_key', 'unknown')),
                       'llm_tier': 'INTERNAL_ON_PREM',
                       'model_revision': model_info.get('model_revision'),
                       'prompt_version': model_info.get('prompt_version'),
                       'confidence_method': 'rule-evidence-coverage-v0.1-UNCALIBRATED'},
        'disclaimer': 'S1은 진단이 아닌 평가 필요 상태. 의료진 판단 전 치료/처방 자동 실행 금지. Confidence is uncalibrated evidence coverage.',
    }
    validate_v012_output(output, documents=docs)
    return output


def validate_v012_output(output: dict, *, documents: list[dict] | None = None) -> None:
    """Validates the *reference example field layout*, not a missing schema file."""
    if not isinstance(output, dict) or set(output) != OUTPUT_FIELDS:
        raise V012ContractError('Incorrect v0.12 output top-level field set')
    if output['agent_id'] != AGENT_ID or output['agent_version'] != AGENT_VERSION:
        raise V012ContractError('Wrong agent ID/version')
    for key in ('execution_id', 'episode_id', 'encounter_id', 'produced_time', 'disclaimer'):
        _nonempty(output[key], key)
    try:
        dt = datetime.fromisoformat(output['produced_time'])
        if dt.tzinfo is None or dt.utcoffset() != timedelta(hours=9):
            raise ValueError('Expected Korea-local +09:00 time')
    except ValueError as exc:
        raise V012ContractError('Invalid produced_time') from exc
    if type(output['confidence']) not in (float, int) or not 0 <= output['confidence'] <= 1:
        raise V012ContractError('confidence must be numeric 0..1')
    if type(output['processing_time_ms']) is not int or output['processing_time_ms'] < 0:
        raise V012ContractError('Invalid processing_time_ms')
    if not isinstance(output['result'], dict) or set(output['result']) != {'screening_result','proposed_state','clinical_label','priority'}:
        raise V012ContractError('Result field shape differs from v0.12')
    if output['result']['screening_result'] not in {'POSITIVE', 'NEGATIVE'}:
        raise V012ContractError('No accepted v0.12 result for REVIEW_REQUIRED')
    if output['result']['proposed_state'] != ('S1' if output['result']['screening_result'] == 'POSITIVE' else 'S0X'):
        raise V012ContractError('Inconsistent proposed_state')
    for name in ('rule_trace', 'text_derived_findings', 'missing_information', 'evidence'):
        if not isinstance(output[name], list):
            raise V012ContractError(f'{name} must be a list')
    if not isinstance(output['model_info'], dict) or not {'rule_set','nlp_model','llm_tier'} <= set(output['model_info']):
        raise V012ContractError('model_info missing contract keys')
    if not isinstance(output['clinical_times'], dict) or set(output['clinical_times']) != {'last_known_well','symptom_discovery','ems_arrival','source_ref','confirmation_status'}:
        raise V012ContractError('Clinical time keys differ from reference')
    for row in output['rule_trace']:
        if not isinstance(row, dict) or set(row) != {'rule','satisfied','basis'} or type(row['satisfied']) is not bool:
            raise V012ContractError('Incorrect rule_trace row')
    for row in output['text_derived_findings']:
        if not isinstance(row, dict) or set(row) != {'finding','label','snomed','source_ref','quote'}:
            raise V012ContractError('Incorrect text_derived_findings row')
    for row in output['evidence']:
        if not isinstance(row, dict) or set(row) != {'source_ref','quote','finding'}:
            raise V012ContractError('Incorrect evidence row')
    if output['result']['screening_result'] == 'POSITIVE' and not output['evidence']:
        raise V012ContractError('S1 transition requires >=1 evidence')
    if documents is not None:
        lookup = {f"document:{d['document_id']}@{d['version']}": d['text'] for d in documents}
        for row in output['evidence'] + output['text_derived_findings']:
            if row['source_ref'] not in lookup or row['quote'] not in lookup[row['source_ref']]:
                raise V012ContractError('Output evidence not grounded in allowed source')


def invoke_v012(request: dict, *, execution_id: str, data_api: Any,
                model: Any, produced_time: str | None = None) -> dict:
    """JLK runtime call: return full dict synchronously, NEVER save to a file.

    The runtime passes an already authorized data_api adapter (P-03). Exceptions
    mean FAILED/NO_STATE_CHANGE, not a fabricated NEGATIVE result. The runtime
    publishes AGENT_RESULT_AVAILABLE and stores output_hash/result_ref itself.
    """
    started = perf_counter()
    payload = validate_v012_input(request)
    _validate_context_scope(payload, data_api)
    docs = _fetch_scoped_documents(payload, data_api)
    try:
        prototype = screen_documents(model, docs, payload['structured_context'])
    except ScreeningResponseError:
        raise  # Do not turn invalid LLM output into an accepted Agent result.
    milliseconds = int((perf_counter()-started)*1000)
    timestamp = produced_time or datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds')
    return to_v012_output(payload, execution_id, prototype, docs,
                          processing_time_ms=milliseconds, produced_time=timestamp)
