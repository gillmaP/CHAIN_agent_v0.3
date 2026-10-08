"""Build the tPA domain result. The Host owns execution status and workflow."""
import json

from ..common import inputs
from .dose import preview
from .facts import Facts
from .policy import LIMITATIONS, POLICY, REQUIRED_FIELDS
from .rules import evaluate


def assessment_status(checks, missing, view):
    results = {check['result'] for check in checks}
    if 'FAIL' in results:
        return 'BLOCKING_FINDING_IDENTIFIED'
    if 'CONFLICT' in results:
        return 'PHYSICIAN_REVIEW_REQUIRED'
    if missing or not view.available('ncct_completed') or view.value('ncct_completed') is False:
        return 'INCOMPLETE_PENDING_DATA'
    return 'PHYSICIAN_REVIEW_REQUIRED'


def run(request, snapshot, services):
    facts = inputs(request, snapshot, {'interim', 'final'})
    view = Facts(facts, request['evaluated_at'], snapshot['known_at'])
    checks = evaluate(view)
    missing = view.missing(REQUIRED_FIELDS)
    assessment = {'schema': 'chain-tpa-assessment/prototype-v1', 'rule_set': POLICY.version,
                  'status': assessment_status(checks, missing, view), 'checks': checks, 'missing_information': missing,
                  'scope_gaps': [check['check_id'] for check in checks if check['result'] == 'NOT_IN_SCOPE'],
                  'items_requiring_physician_confirmation': [check['check_id'] for check in checks
                      if check['result'] in {'PASS_UNCONFIRMED', 'REQUIRES_PHYSICIAN_READ',
                                            'REQUIRES_PHYSICIAN_REVIEW', 'PASS_WITH_FLAG', 'CONFLICT'}],
                  'dose_preview': preview(view), 'limitations': list(LIMITATIONS),
                  'recommendation_type': 'DECISION_SUPPORT_ONLY', 'physician_decision_required': True}
    result = {'mode': request['mode'], 'evidence_package': facts,
              'assessment': assessment, 'mock_only': True}
    try:
        json.dumps(result, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError('tPA domain output must be finite JSON') from exc
    return result
