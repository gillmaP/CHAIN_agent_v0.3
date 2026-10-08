"""Initial S1 Summary invocation: retrieve, extract, validate, reconcile, return."""
import copy
import json
import re

from .contract import (
    QUESTION_CATALOG, SCHEMA_VERSION, canonical_questions, evidence_entry,
    finalize_facts, validate_model_payload,
)
from .data_contract import resolve
from .input_audit import InputAudit, InputResolutionError


def _structured_facts(resources, questions):
    """Read structured records deterministically; absence from a list is not false."""
    facts, missing = [], []

    def add(question, ref, record):
        if question in questions:
            facts.append({'question': question, 'status': 'documented', 'value': True,
                          'evidence': [{'source_ref': ref, 'record': copy.deepcopy(record)}]})

    ref = 'medication:active'
    if ref in resources and ({'anticoagulant_use', 'antiplatelet_use'} & set(questions)):
        data = resources[ref]
        meds = data.get('medications')
        if not isinstance(meds, list):
            raise ValueError('medication:active must contain a medications array')
        for row in meds:
            if not isinstance(row, dict):
                raise ValueError('Invalid medication row')
            if row.get('status') != 'ACTIVE':
                continue
            flags = row.get('drug_class_flags', {})
            for question, key in (('anticoagulant_use', 'anticoagulant'), ('antiplatelet_use', 'antiplatelet')):
                if question not in questions:
                    continue
                value = flags.get(key) if isinstance(flags, dict) else None
                if value is True:
                    add(question, ref, row)
                elif value is not False:
                    missing.append(f'{question}: active medication row has no deterministic {key} classification')
        coverage = data.get('coverage')
        if coverage:
            missing.append(f'Medication source limit: {coverage}')

    ref = 'condition:problem_list'
    if ref in resources and 'previous_stroke' in questions:
        rows = resources[ref].get('conditions')
        if not isinstance(rows, list):
            raise ValueError('condition:problem_list must contain a conditions array')
        for row in rows:
            if not isinstance(row, dict) or row.get('category') != 'PROBLEM_LIST':
                continue
            if row.get('status') in ('PROVISIONAL', 'ENTERED_IN_ERROR', 'RETRACTED'):
                continue
            code = row.get('code')
            if isinstance(code, str) and re.match(r'^(I6[0-9]|G45|Z86\.73)', code):
                add('previous_stroke', ref, row)
            elif not isinstance(code, str) or not code:
                missing.append('previous_stroke: an uncoded problem-list row needs review')

    ref = 'encounter_history:6m'
    if ref in resources and ({'recent_surgery', 'recent_bleeding'} & set(questions)):
        data = resources[ref]
        rows = data.get('encounters')
        if data.get('window_months') != 6 or not isinstance(rows, list):
            raise ValueError('encounter_history:6m must contain a six-month encounters array')
        for row in rows:
            if not isinstance(row, dict) or row.get('current'):
                continue
            surgery = row.get('surgery')
            bleeding = row.get('bleeding_event')
            procedures = row.get('procedures')
            if surgery is True:
                add('recent_surgery', ref, row)
            elif surgery is not False:
                missing.append('recent_surgery: a six-month encounter row has an unresolved surgery flag')
            if bleeding is True:
                add('recent_bleeding', ref, row)
            elif bleeding is not False:
                missing.append('recent_bleeding: a six-month encounter row has an unresolved bleeding flag')
            if not isinstance(procedures, list):
                missing.append('recent_surgery: an encounter has an unclassified procedure list')
            elif procedures:
                missing.append('recent_surgery: a procedure list needs classification')
        missing.append('Surgery/bleeding search is limited to the supplied local six-month encounter history.')
    return facts, missing


def run_history(request, snapshot, services):
    """One S1 request returns a complete typed Summary object to the runtime."""
    if snapshot is not None:
        raise ValueError('Reference-based S1 Summary expects snapshot=None')
    questions = canonical_questions(request.get('questions'))
    reader = getattr(services, 'summary_data_api', None)
    extractor = getattr(services, 'summary_extractor', None)
    audit = InputAudit(request, extractor)
    save_input = getattr(services, 'summary_input_observer', None)
    try:
        resources = resolve(request, reader, audit=audit)
        # Validate structured resources before model inference; no partial success.
        try:
            structured, missing = _structured_facts(resources, questions)
        except ValueError as exc:
            audit.metadata['validation_error'] = 'structured_resource_invalid'
            raise InputResolutionError('Structured resource validation failed') from exc
        audit.complete()
    finally:
        if save_input is not None:
            save_input(audit.snapshot())
    documents = {ref: data for ref, data in resources.items() if ref.startswith('document:')}
    if documents:
        if extractor is None or not callable(getattr(extractor, 'extract', None)):
            raise ValueError('services.summary_extractor.extract is required when narrative documents are supplied')
        model_payload = extractor.extract(copy.deepcopy(documents), list(questions))
    else:
        model_payload = {'facts': [], 'reviewed_documents': []}
    validate_model_payload(model_payload, documents, questions)
    items = finalize_facts(model_payload, documents, questions, extra_facts=structured, evidence_sources=resources)
    for item in items:
        if item['status'] in ('not_stated', 'explicitly_unknown', 'conflicting', 'not_applicable'):
            missing.append(f'{item["question"]}: {item["status"]}')
    return {
        'schema_version': SCHEMA_VERSION,
        'episode_id': request['episode_id'],
        'encounter_id': request['encounter_id'],
        'input_references': list(request['input_references']),
        'questions': list(questions),
        'items': items,
        'missing_information': list(dict.fromkeys(missing)),
        'model_info': {
            'rule_set': 'summary-s1-reconcile/v1',
            'llm_tier': 'INTERNAL_ON_PREM',
            'model_key': getattr(extractor, 'model_key', None),
            'extraction_method': getattr(extractor, 'method', 'deterministic-only' if not documents else None),
            'confidence_policy': 'No uncalibrated confidence score is emitted.',
        },
        'mock_only': bool(getattr(reader, 'mock_only', False)),
    }
