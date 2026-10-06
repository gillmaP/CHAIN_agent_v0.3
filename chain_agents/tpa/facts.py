"""Read scoped Facts without changing their status or provenance."""
from __future__ import annotations

import copy
import math
from datetime import datetime

from ..common import MISSING_STATUSES


def timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Expected an ISO timestamp') from exc
    if parsed.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    return parsed


def number(value, field: str, *, minimum=0, maximum=None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{field} must be a number, not a boolean or text')
    if not math.isfinite(value) or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f'{field} is outside its supported numeric range')
    return value


class Facts:
    """A read-only view; Runtime remains responsible for full wire validation."""

    def __init__(self, facts: dict, evaluated_at: str, known_at: str):
        self.raw = facts
        self.now = timestamp(evaluated_at)
        if timestamp(known_at) > self.now:
            raise ValueError('Evaluation precedes the input Snapshot')
        for name, fact in facts.items():
            if not isinstance(fact, dict):
                raise ValueError(f'{name} must be a Fact object')
            if not {'value', 'status', 'source_ref', 'source_time', 'known_at'} <= fact.keys():
                raise ValueError(f'{name} is missing Fact metadata')
            if not isinstance(fact['status'], str) or not isinstance(fact['source_ref'], dict):
                raise ValueError(f'{name} has invalid Fact metadata')
            if timestamp(fact['source_time']) > self.now or timestamp(fact['known_at']) > timestamp(known_at):
                raise ValueError(f'{name} contains future evidence')

    def available(self, name: str) -> bool:
        fact = self.raw.get(name)
        return bool(fact and fact['value'] is not None and fact['status'] not in MISSING_STATUSES
                    and fact['status'] in {'AVAILABLE', 'CONFIRMED', 'CONSISTENT', 'PRESENT'})

    def value(self, name: str):
        return self.raw[name]['value']

    def unit(self, name: str):
        return self.raw[name].get('unit')

    def missing(self, names) -> list[str]:
        return [name for name in names if not self.available(name)]

    def unavailable_result(self, names) -> str:
        if any(self.raw.get(name, {}).get('status') == 'CONFLICT' for name in names):
            return 'CONFLICT'
        if all(name not in self.raw for name in names):
            return 'NOT_IN_SCOPE'
        return 'PENDING'

    def evidence(self, names) -> list[dict]:
        return [dict(field=name, **copy.deepcopy({k: v for k, v in self.raw[name].items() if k != 'value'}))
                for name in names if name in self.raw]
