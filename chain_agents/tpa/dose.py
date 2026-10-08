"""Deterministic dose arithmetic; produces a preview, never a prescription."""
from decimal import Decimal, ROUND_HALF_UP

from .facts import number


def calculate(weight_kg) -> list[dict]:
    number(weight_kg, 'weight_kg')
    if weight_kg <= 0:
        raise ValueError('Positive measured weight is required')
    weight = Decimal(str(weight_kg))
    alteplase = min(weight * Decimal('0.9'), Decimal('90'))
    bolus = alteplase * Decimal('0.1')
    tenecteplase = min(weight * Decimal('0.25'), Decimal('25'))

    def display(value):
        return float(value.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))

    return [
        {'drug': 'alteplase', 'total_mg': float(alteplase), 'bolus_mg': float(bolus),
         'infusion_mg': float(alteplase - bolus), 'bolus_duration_seconds': 60,
         'infusion_duration_minutes': 60,
         'display_rounded_mg': {'total': display(alteplase), 'bolus': display(bolus),
                                'infusion': display(alteplase - bolus)},
         'source_ids': ['ACTIVASE_LABEL']},
        {'drug': 'tenecteplase', 'total_mg': float(tenecteplase), 'administration': 'SINGLE_IV_BOLUS',
         'display_rounded_mg': {'total': display(tenecteplase)}, 'source_ids': ['KSS2025']},
    ]


def preview(facts) -> dict:
    weight = None
    reason = 'WEIGHT_NOT_AVAILABLE'
    if facts.available('weight_kg'):
        weight = number(facts.value('weight_kg'), 'weight_kg')
        if weight <= 0:
            raise ValueError('Positive measured weight is required')
        # The field contract itself is kg; a conflicting explicit unit is rejected.
        if facts.unit('weight_kg') not in (None, 'kg'):
            raise ValueError('weight_kg must use kg')
        reason = 'MEASURED_WEIGHT_ARITHMETIC_ONLY'
    return {'weight_kg': weight, 'options': calculate(weight) if weight is not None else [],
            'basis': reason, 'evidence': facts.evidence(('weight_kg',)),
            'physician_confirmation_required': True, 'auto_order': False, 'auto_administration': False}
