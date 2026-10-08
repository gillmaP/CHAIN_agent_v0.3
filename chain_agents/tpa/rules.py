"""Scoped, deterministic IVT review checks. No I/O, inference or state changes."""
from __future__ import annotations

from datetime import timedelta

from .facts import Facts, number, timestamp
from .policy import POLICY


def check(facts, check_id, label, fields, result, *, value=None, detail='', sources=()):
    return {'check_id': check_id, 'label': label, 'result': result, 'value': value,
            'detail': detail, 'evidence': facts.evidence(fields), 'source_ids': list(sources)}


def pending(facts, check_id, label, fields, sources=()):
    return check(facts, check_id, label, fields, facts.unavailable_result(fields),
                 detail='Missing, unavailable or outside the requested scope; no value inferred.', sources=sources)


def time_window(facts: Facts) -> dict:
    fields = ('lkw',)
    args = (facts, 'C01_TIME_WINDOW', 'LKW standard 4.5-hour window', fields)
    if facts.missing(fields):
        return pending(*args, sources=('AHA2026',))
    lkw = timestamp(facts.value('lkw'))
    if lkw > facts.now:
        raise ValueError('LKW cannot be later than evaluated_at')
    elapsed = (facts.now - lkw).total_seconds()
    return check(*args, 'PASS' if elapsed <= POLICY.standard_window_seconds else 'REQUIRES_PHYSICIAN_REVIEW',
                 value={'elapsed_seconds': elapsed, 'deadline': (lkw + timedelta(seconds=POLICY.standard_window_seconds)).isoformat()},
                 detail='Unknown-onset/extended-window imaging selection requires specialist review.', sources=('AHA2026',))


def ncct(facts: Facts) -> dict:
    fields = ('ncct_completed', 'ncct_order_id', 'ct_order_id')
    args = (facts, 'C02_NO_ICH_ON_NCCT', 'NCCT completion and order binding', fields)
    if facts.available('ncct_completed') and not isinstance(facts.value('ncct_completed'), bool):
        raise ValueError('ncct_completed must be an explicit boolean')
    if facts.missing(fields):
        return pending(*args, sources=('ACTIVASE_LABEL',))
    for field in fields[1:]:
        if not isinstance(facts.value(field), str) or not facts.value(field).strip():
            raise ValueError(f'{field} must be a nonempty order ID')
    completed = facts.value('ncct_completed')
    matching = facts.value('ncct_order_id') == facts.value('ct_order_id')
    result = 'CONFLICT' if not matching else 'REQUIRES_PHYSICIAN_READ' if completed else 'PENDING'
    return check(*args, result, value={'completed': completed, 'order_matches': matching},
                 detail='Completion never establishes absence of hemorrhage.', sources=('ACTIVASE_LABEL',))


def platelet(facts: Facts) -> dict:
    args = (facts, 'C03_PLATELET_GE_100K', 'Platelets >=100,000/uL', ('platelet_count',))
    if not facts.available('platelet_count'):
        return pending(*args, sources=('ESO2021',))
    value = number(facts.value('platelet_count'), 'platelet_count')
    unit = facts.unit('platelet_count')
    factors = {'/uL': 1, '/µL': 1, '/μL': 1, '/mm3': 1, '/mm^3': 1,
               '10^3/uL': 1000, '10^9/L': 1000, '10*9/L': 1000}
    if unit not in factors:
        return check(*args, 'REQUIRES_PHYSICIAN_REVIEW', value={'reported': value, 'unit': unit},
                     detail='Platelet unit needs confirmation; no unit assumed.', sources=('ESO2021',))
    value *= factors[unit]
    return check(*args, 'PASS' if value >= POLICY.platelet_min_per_ul else 'FAIL',
                 value={'per_ul': value}, sources=('ESO2021',))


def inr(facts: Facts) -> dict:
    args = (facts, 'C04_INR_LE_1_7', 'INR <=1.7', ('inr',))
    if not facts.available('inr'):
        return pending(*args, sources=('ESO2021',))
    value = number(facts.value('inr'), 'inr')
    if value <= 0:
        raise ValueError('Positive INR is required')
    if facts.unit('inr') not in (None, '', '1', '{INR}'):
        raise ValueError('INR must be dimensionless')
    return check(*args, 'PASS' if value <= POLICY.inr_max else 'FAIL', value=value,
                 detail='INR alone does not clear DOAC/heparin exposure.', sources=('ESO2021',))


def anticoagulant(facts: Facts) -> dict:
    args = (facts, 'C05_NO_ANTICOAGULANT', 'Anticoagulant exposure review', ('anticoagulant',))
    if not facts.available('anticoagulant'):
        return pending(*args, sources=('ESO2021',))
    value = facts.value('anticoagulant')
    negative = value is False
    if isinstance(value, str):
        if value in {'NO_EVIDENCE', 'NONE_DOCUMENTED', 'NONE'}:
            negative = True
        elif value not in {'PRESENT', 'YES'}:
            return check(*args, 'REQUIRES_PHYSICIAN_REVIEW', value=value,
                         detail='Exposure text is not parsed into a clinical fact.', sources=('ESO2021',))
    elif not isinstance(value, bool):
        return check(*args, 'REQUIRES_PHYSICIAN_REVIEW', value=value,
                     detail='Exposure, drug, last dose, renal function and specific assays require review.', sources=('ESO2021',))
    fact = facts.raw['anticoagulant']
    confirmed = (value is False and fact['status'] != 'NO_EVIDENCE'
                 and fact.get('confirmation_status') == 'PHYSICIAN_CONFIRMED')
    result = 'PASS' if confirmed else 'PASS_UNCONFIRMED' if negative else 'REQUIRES_PHYSICIAN_REVIEW'
    return check(*args, result, value=value,
                 detail='No evidence is not confirmed absence. Do not automatically exclude all anticoagulant users.', sources=('ESO2021',))


def blood_pressure(facts: Facts) -> dict:
    fields = ('sbp', 'dbp')
    args = (facts, 'C06_BP_LT_185_110', 'BP <185/110 mmHg (mock boundary)', fields)
    if facts.missing(fields):
        return pending(*args, sources=('ESO2021', 'CHAIN_MOCK'))
    sbp, dbp = [number(facts.value(field), field) for field in fields]
    if sbp <= 0 or dbp <= 0:
        raise ValueError('Positive blood pressure is required')
    value = {'sbp': sbp, 'dbp': dbp}
    if any(facts.unit(field) != 'mmHg' for field in fields):
        return check(*args, 'REQUIRES_PHYSICIAN_REVIEW', value=value,
                     detail='BP unit needs confirmation; no unit assumed.', sources=('ESO2021',))
    stale = any((facts.now - timestamp(facts.raw[field]['source_time'])).total_seconds()
                > POLICY.bp_recheck_seconds for field in fields)
    exceeded = sbp >= POLICY.sbp_limit or dbp >= POLICY.dbp_limit
    result = 'REQUIRES_PHYSICIAN_REVIEW' if exceeded else 'PASS_WITH_FLAG' if stale else 'PASS'
    return check(*args, result, value=value,
                 detail='Recheck/correct BP before physician assessment.' if exceeded else
                        'Recheck BP: local demo freshness limit is 5 minutes.' if stale else '',
                 sources=('ESO2021', 'CHAIN_MOCK'))


def glucose(facts: Facts) -> dict:
    args = (facts, 'C07_GLUCOSE_50_400', 'Glucose 50-400 mg/dL (mock range)', ('glucose',))
    if not facts.available('glucose'):
        return pending(*args, sources=('CHAIN_MOCK',))
    value = number(facts.value('glucose'), 'glucose')
    unit = facts.unit('glucose')
    if unit not in {'mg/dL', 'mmol/L'}:
        return check(*args, 'REQUIRES_PHYSICIAN_REVIEW', value={'reported': value, 'unit': unit},
                     detail='Glucose unit needs confirmation; no unit assumed.', sources=('CHAIN_MOCK',))
    value *= 18 if unit == 'mmol/L' else 1
    passed = POLICY.glucose_mock_low <= value <= POLICY.glucose_mock_high
    return check(*args, 'PASS' if passed else 'REQUIRES_PHYSICIAN_REVIEW', value={'mg_dl': value},
                 detail='Mock range only. Correct/reassess abnormal glucose; no automatic IVT exclusion.', sources=('CHAIN_MOCK',))


def history(facts, check_id, label, field, sources):
    args = (facts, check_id, label, (field,))
    if not facts.available(field):
        return pending(*args, sources=sources)
    return check(*args, 'REQUIRES_PHYSICIAN_REVIEW', value=facts.value(field),
                 detail='History is displayed without free-text interpretation or a confirmed negative.', sources=sources)


def nihss(facts: Facts) -> dict:
    args = (facts, 'C10_NIHSS', 'NIHSS (information only)', ('nihss',))
    if not facts.available('nihss'):
        return pending(*args, sources=('AHA2026',))
    value = number(facts.value('nihss'), 'nihss', maximum=42)
    if int(value) != value:
        raise ValueError('NIHSS must be a whole-number total')
    return check(*args, 'INFO', value=value,
                 detail='Disabling deficit requires physician assessment; no NIHSS exclusion cutoff.', sources=('AHA2026',))


def age(facts: Facts) -> dict:
    args = (facts, 'C12_AGE', 'Age (information only)', ('age',))
    if not facts.available('age'):
        return pending(*args, sources=('ESO2021',))
    value = number(facts.value('age'), 'age', maximum=130)
    if int(value) != value:
        raise ValueError('Age must be a whole number')
    return check(*args, 'INFO' if value >= 18 else 'REQUIRES_PHYSICIAN_REVIEW', value=value,
                 detail='Advanced age alone is not an automatic exclusion; pediatric use is outside this prototype.', sources=('ESO2021',))


def evaluate(facts: Facts) -> list[dict]:
    return [time_window(facts), ncct(facts), platelet(facts), inr(facts), anticoagulant(facts),
            blood_pressure(facts), glucose(facts),
            history(facts, 'C08_NO_RECENT_SURGERY_BLEED', 'Recent surgery/bleeding review',
                    'recent_surgery_or_bleeding', ('ESO2021', 'ACTIVASE_LABEL')),
            history(facts, 'C09_NO_PRIOR_ICH_OR_RECENT_STROKE', 'ICH/recent stroke history review',
                    'previous_stroke', ('CHAIN_MOCK',)), nihss(facts),
            history(facts, 'C11_ANTIPLATELET', 'Antiplatelet history review',
                    'antiplatelet', ('ESO2021',)), age(facts)]
