"""Typed request/output contract for the initial S1 Summary invocation."""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone

SCHEMA_VERSION = 'summary-s1-fields/v1'
STATUSES = {'documented', 'not_stated', 'explicitly_unknown', 'conflicting', 'not_applicable'}
TIME_KINDS = {'point', 'approximate', 'interval', 'before', 'after', 'partial'}
TIME_PRECISIONS = {'second', 'minute', 'hour', 'day', 'unknown'}
TIME_KEYS = {'kind', 'start', 'end', 'precision', 'original_text'}

# The orchestrator sends stable question IDs. It does not send free-text queries for
# the initial S1 call. These definitions are supplied to the LLM and validators.
QUESTION_CATALOG = {
    'anticoagulant_use': {
        'type': 'boolean',
        'value_schema': 'JSON boolean only: true means an explicit current-use statement; false means an explicit current non-use statement. For documented use a boolean, never a drug name. For explicitly_unknown or not_stated use null, following the common status rules.',
        'scope': 'Whether this patient is currently taking any anticoagulant.',
        'rules': 'true=explicit current use; false=explicit current non-use. Drug name/dose are evidence, not this value. Exclude family members and discontinued drugs.',
    },
    'antiplatelet_use': {
        'type': 'boolean',
        'value_schema': 'JSON boolean only: true means an explicit current-use statement; false means an explicit current non-use statement. For documented use a boolean, never a drug name. For explicitly_unknown or not_stated use null, following the common status rules.',
        'scope': 'Whether this patient is currently taking any antiplatelet medication.',
        'rules': 'Use the same boolean convention as anticoagulant_use. Aspirin/ASA is antiplatelet, not anticoagulant. Exclude family members and discontinued drugs.',
    },
    'recent_surgery': {
        'type': 'boolean',
        'value_schema': 'JSON boolean only: true or false. null is allowed only when status is explicitly_unknown or another non-documented status.',
        'scope': 'Whether this patient had surgery within the recent-history window stated by the source/request (default six months for this S1 prototype).',
        'rules': 'true/false requires explicit evidence. Do not use a denial of surgery to answer recent_bleeding.',
    },
    'recent_bleeding': {
        'type': 'boolean',
        'value_schema': 'JSON boolean only: true or false. null is allowed only when status is explicitly_unknown or another non-documented status.',
        'scope': 'Whether this patient had a bleeding event within the recent-history window stated by the source/request (default six months for this S1 prototype).',
        'rules': 'true/false requires explicit evidence. Do not use a denial of bleeding to answer recent_surgery.',
    },
    'previous_stroke': {
        'type': 'boolean',
        'value_schema': 'JSON boolean only: true or false. null is allowed only when status is explicitly_unknown or another non-documented status.',
        'scope': 'Whether this patient personally had a past stroke or TIA.',
        'rules': 'Exclude family history and the current suspected stroke episode. Explicitly stated no history is false.',
    },
    'lkw_records': {
        'type': 'time',
        'value_schema': {
            'exact_keys': ['kind', 'start', 'end', 'precision', 'original_text'],
            'timestamp_format': 'Use YYYY-MM-DDTHH:MM:SS+09:00 for Korean local date-times. A minute-level time uses seconds :00 and precision=minute; an hour-level time uses :00:00 and precision=hour. Preserve the source precision.',
            'kind_shapes': {
                'point': 'start=the normalized timestamp; end=null; precision reflects the source.',
                'approximate': 'start=the normalized approximate timestamp (for example 15시쯤 -> 15:00:00 with precision=hour); end=null; retain the qualifier in original_text.',
                'interval': 'start=the lower-bound timestamp; end=the upper-bound timestamp; precision reflects the source.',
                'before': 'start=null; end=the stated upper-bound timestamp.',
                'after': 'start=the stated lower-bound timestamp; end=null.',
                'partial': 'For a known date without a known time, use start=YYYY-MM-DD, end=null, precision=day. If no component can be normalized, both endpoints may be null only when precision=unknown; preserve the supplied phrase in original_text.'
            },
            'original_text': 'Copy the shortest contiguous verbatim source phrase that states the LKW value, including approximation or range wording. Do not paraphrase.'
        },
        'scope': 'The last-known-well time for the current episode, when the patient was last known at their neurologic baseline.',
        'rules': 'Do not substitute symptom onset, discovery/recognition time, or note-entry time. Preserve approximate/interval precision and the original wording. Multiple agreeing sources become one documented value with multiple evidence entries; incompatible times become conflicting alternatives. For point and approximate values, end must be null; only interval uses both endpoints.',
    },
}
QUESTION_ORDER = tuple(QUESTION_CATALOG)
REQUEST_ALIASES = {'recent_surgery_or_bleeding': ('recent_surgery', 'recent_bleeding')}


def normalize_text(value):
    return ''.join(unicodedata.normalize('NFKC', str(value)).casefold().split())


def canonical_questions(request_questions):
    if not isinstance(request_questions, list) or not request_questions:
        raise ValueError('questions must be a non-empty list of question IDs')
    expanded = []
    for question in request_questions:
        if question in REQUEST_ALIASES:
            expanded.extend(REQUEST_ALIASES[question])
        elif question in QUESTION_CATALOG:
            expanded.append(question)
        else:
            raise ValueError(f'Unsupported Summary question: {question}')
    if 'anticoagulant_use' in expanded and 'antiplatelet_use' not in expanded:
        expanded.append('antiplatelet_use')
    requested = set(expanded)
    return [q for q in QUESTION_ORDER if q in requested]


def evidence_entry(source_ref, quote):
    return {'source_ref': source_ref, 'quote': quote}


def validate_value(value, question):
    spec = QUESTION_CATALOG[question]
    if value is None:
        return ['documented value must not be null']
    if spec['type'] == 'boolean':
        return [] if type(value) is bool else ['value must be a JSON boolean true or false']
    if spec['type'] != 'time':
        return ['unknown question value type']
    if not isinstance(value, dict) or set(value) != TIME_KEYS:
        return ['time value requires kind, start, end, precision, original_text']
    errors = []
    if value['kind'] not in TIME_KINDS:
        errors.append('invalid time kind')
    if value['precision'] not in TIME_PRECISIONS:
        errors.append('invalid time precision')
    if not isinstance(value['original_text'], str) or not value['original_text'].strip():
        errors.append('original_text is required')
    for key in ('start', 'end'):
        raw = value[key]
        if raw is None:
            continue
        if not isinstance(raw, str):
            errors.append(f'{key} must be an ISO date/time string or null')
            continue
        try:
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
                datetime.fromisoformat(raw)
                if value['kind'] != 'partial' or value['precision'] != 'day':
                    errors.append('date-only time must use kind=partial and precision=day')
            else:
                parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
                if parsed.tzinfo is None:
                    errors.append(f'{key} timestamp requires a timezone')
        except ValueError:
            errors.append(f'{key} is not a valid ISO date/time')
    if value['kind'] in ('point', 'approximate', 'after') and (value['start'] is None or value['end'] is not None):
        errors.append(f'{value["kind"]} requires start and null end')
    if value['kind'] == 'before' and (value['start'] is not None or value['end'] is None):
        errors.append('before requires null start and end')
    if value['kind'] == 'interval' and (value['start'] is None or value['end'] is None):
        errors.append('interval requires start and end')
    if value['kind'] == 'partial' and value['start'] is None and value['end'] is None and value['precision'] != 'unknown':
        errors.append('partial time without normalized endpoints requires precision=unknown')
    if value['kind'] == 'interval' and value['start'] and value['end']:
        try:
            start = datetime.fromisoformat(value['start'].replace('Z', '+00:00'))
            end = datetime.fromisoformat(value['end'].replace('Z', '+00:00'))
            if start > end:
                errors.append('interval endpoints are reversed')
        except ValueError:
            pass
    return errors


def _structured_records(resource):
    if not isinstance(resource, dict):
        return []
    for key in ('medications', 'conditions', 'encounters'):
        value = resource.get(key)
        if isinstance(value, list):
            return value
    return []


def validate_evidence(evidence, sources, required):
    if not isinstance(evidence, list):
        return ['evidence must be an array']
    errors = []
    if required and not evidence:
        errors.append('evidence is required')
    for item in evidence:
        if not isinstance(item, dict) or 'source_ref' not in item:
            errors.append('evidence entry requires source_ref')
            continue
        ref = item['source_ref']
        if ref not in sources:
            errors.append(f'unknown evidence source_ref: {ref}')
            continue
        if set(item) == {'source_ref', 'quote'}:
            quote = item['quote']
            source_text = sources[ref].get('text')
            if not isinstance(source_text, str) or not isinstance(quote, str) or not quote.strip() or normalize_text(quote) not in normalize_text(source_text):
                errors.append(f'quote is not present in cited document: {ref}')
        elif set(item) == {'source_ref', 'record'}:
            if item['record'] not in _structured_records(sources[ref]):
                errors.append(f'structured evidence record is not present in source: {ref}')
        else:
            errors.append('evidence entry must be {source_ref, quote} or {source_ref, record}')
    return errors


def validate_model_payload(payload, documents, questions):
    """Validate source-backed model candidates. Absence and conflicts are code-owned."""
    if not isinstance(payload, dict) or set(payload) != {'facts', 'reviewed_documents'}:
        raise ValueError('model payload requires exactly facts and reviewed_documents')
    reviewed = payload['reviewed_documents']
    if not isinstance(reviewed, list) or len(reviewed) != len(set(reviewed)) or set(reviewed) != set(documents):
        raise ValueError('every supplied document must be reviewed exactly once')
    if not isinstance(payload['facts'], list):
        raise ValueError('facts must be an array')
    errors = []
    for index, item in enumerate(payload['facts']):
        at = f'facts[{index}]'
        if not isinstance(item, dict) or set(item) != {'question', 'status', 'value', 'evidence'}:
            expected = {'question', 'status', 'value', 'evidence'}
            actual = set(item) if isinstance(item, dict) else set()
            errors.append(f'{at} requires exactly question, status, value, evidence; missing={sorted(expected - actual)}, extra={sorted(actual - expected)}')
            continue
        question = item['question']
        if question not in questions:
            errors.append(f'{at} has unrequested question: {question}')
            continue
        status = item['status']
        if status == 'documented':
            errors.extend(f'{at}: {err}' for err in validate_value(item['value'], question))
            errors.extend(f'{at}: {err}' for err in validate_evidence(item['evidence'], documents, True))
            if question == 'lkw_records' and isinstance(item['value'], dict):
                original_text = item['value'].get('original_text', '')
                if not any(
                    isinstance(evidence, dict)
                    and isinstance(evidence.get('quote'), str)
                    and normalize_text(original_text) in normalize_text(evidence['quote'])
                    for evidence in item['evidence']
                ):
                    errors.append(f'{at}: original_text must appear verbatim within at least one cited LKW quote')
        elif status == 'explicitly_unknown':
            if item['value'] is not None:
                errors.append(f'{at}: explicitly_unknown requires value=null')
            errors.extend(f'{at}: {err}' for err in validate_evidence(item['evidence'], documents, True))
        elif status == 'not_stated':
            if item['value'] is not None or item['evidence'] != []:
                errors.append(f'{at}: not_stated requires value=null and evidence=[]')
        else:
            errors.append(f'{at}: model may emit documented, explicitly_unknown or not_stated, not {status!r}')
    if errors:
        raise ValueError('; '.join(errors))
    return payload


def canonical_value(value, question):
    if QUESTION_CATALOG[question]['type'] != 'time' or not isinstance(value, dict):
        return value
    result = {k: value.get(k) for k in ('kind', 'start', 'end', 'precision')}
    for key in ('start', 'end'):
        raw = result[key]
        if isinstance(raw, str) and 'T' in raw:
            try:
                parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
                if parsed.tzinfo:
                    result[key] = parsed.astimezone(timezone.utc).isoformat()
            except ValueError:
                pass
    if result['start'] is None and result['end'] is None:
        result['original_text'] = normalize_text(value.get('original_text', ''))
    return result


def _dedupe_evidence(evidence):
    seen, result = set(), []
    for item in evidence:
        key = (item['source_ref'], json.dumps(item.get('quote', item.get('record')), sort_keys=True, ensure_ascii=False))
        if key not in seen:
            seen.add(key)
            result.append(dict(item))
    return result


def finalize_facts(payload, documents, questions, extra_facts=None, evidence_sources=None):
    """Build one deterministic, persistable field per requested question."""
    validate_model_payload(payload, documents, questions)
    grouped = {q: [] for q in questions}
    for fact in list(payload['facts']) + list(extra_facts or []):
        if fact.get('question') not in grouped:
            raise ValueError(f'Extra fact has unrequested question: {fact.get("question")}')
        grouped[fact['question']].append(fact)
    output = []
    for question in questions:
        facts = grouped[question]
        documented = [f for f in facts if f['status'] == 'documented']
        unknown = [f for f in facts if f['status'] == 'explicitly_unknown']
        if documented:
            values = {}
            for fact in documented:
                key = json.dumps(canonical_value(fact['value'], question), sort_keys=True, ensure_ascii=False)
                values.setdefault(key, {'value': fact['value'], 'evidence': []})
                values[key]['evidence'].extend(fact['evidence'])
            if len(values) > 1:
                alternatives = [
                    {'value': entry['value'], 'evidence': _dedupe_evidence(entry['evidence'])}
                    for _, entry in sorted(values.items())
                ]
                output.append({'question': question, 'status': 'conflicting', 'value': None, 'evidence': [], 'alternatives': alternatives})
            else:
                entry = next(iter(values.values()))
                output.append({'question': question, 'status': 'documented', 'value': entry['value'],
                               'evidence': _dedupe_evidence(entry['evidence']), 'alternatives': []})
        elif unknown:
            evidence = _dedupe_evidence([e for fact in unknown for e in fact['evidence']])
            output.append({'question': question, 'status': 'explicitly_unknown', 'value': None, 'evidence': evidence, 'alternatives': []})
        else:
            output.append({'question': question, 'status': 'not_stated', 'value': None, 'evidence': [], 'alternatives': []})
    validate_final_items(output, questions, evidence_sources or documents)
    return output


def validate_final_items(items, questions, documents):
    if not isinstance(items, list):
        raise ValueError('items must be an array')
    seen = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict) or set(item) != {'question', 'status', 'value', 'evidence', 'alternatives'}:
            raise ValueError(f'items[{index}] requires question, status, value, evidence, alternatives')
        q, status = item['question'], item['status']
        if q not in questions or q in seen:
            raise ValueError(f'items[{index}] has an unrequested or duplicate question')
        seen.add(q)
        if status not in STATUSES:
            raise ValueError(f'items[{index}] has invalid status')
        if not isinstance(item['alternatives'], list):
            raise ValueError(f'items[{index}].alternatives must be an array')
        if status == 'documented':
            errors = validate_value(item['value'], q) + validate_evidence(item['evidence'], documents, True)
            if item['alternatives']:
                errors.append('documented field must have alternatives=[]')
        elif status in ('not_stated', 'explicitly_unknown', 'not_applicable'):
            errors = []
            if item['value'] is not None:
                errors.append(f'{status} requires value=null')
            errors += validate_evidence(item['evidence'], documents, status in ('explicitly_unknown', 'not_applicable'))
            if item['alternatives']:
                errors.append(f'{status} requires alternatives=[]')
            if status == 'not_stated' and item['evidence']:
                errors.append('not_stated requires evidence=[]')
        else:
            errors = []
            if item['value'] is not None or item['evidence']:
                errors.append('conflicting requires value=null and evidence=[]')
            if len(item['alternatives']) < 2:
                errors.append('conflicting requires at least two alternatives')
            seen_values = set()
            for alternative in item['alternatives']:
                if not isinstance(alternative, dict) or set(alternative) != {'value', 'evidence'}:
                    errors.append('conflict alternative requires value and evidence')
                    continue
                errors += validate_value(alternative['value'], q)
                errors += validate_evidence(alternative['evidence'], documents, True)
                seen_values.add(json.dumps(canonical_value(alternative['value'], q), sort_keys=True, ensure_ascii=False))
            if len(seen_values) < 2:
                errors.append('conflicting alternatives must contain distinct values')
        if errors:
            raise ValueError(f'items[{index}]: ' + '; '.join(errors))
    if seen != set(questions):
        raise ValueError('every requested question must have exactly one final item')
    return True
