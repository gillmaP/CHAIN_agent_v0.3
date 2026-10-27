"""Time arithmetic without inventing an exact time from an uncertain record."""
from datetime import date, timedelta
from .facts import timestamp


def time_window(view, policy):
    result = {'status': 'UNKNOWN', 'evaluated_at': view.now.isoformat(),
              'lkw': None, 'elapsed_seconds': None, 'deadline': None, 'remaining_seconds': None,
              'basis': 'STANDARD_WINDOW_ONLY', 'protocol_id': policy.protocol_id, 'protocol_version': policy.version}
    if not view.available('lkw'):
        return result
    value = view.value('lkw')
    result['lkw'] = value
    if isinstance(value, dict):
        if set(value) != {'kind', 'start', 'end', 'precision', 'original_text'}:
            raise ValueError('Invalid Summary time object')
        if value['kind'] not in {'point', 'approximate', 'interval', 'before', 'after', 'partial'}:
            raise ValueError('Unknown time kind')
        if value['precision'] not in {'second', 'minute', 'hour', 'day', 'unknown'} or not isinstance(value['original_text'], str):
            raise ValueError('Invalid time precision or original text')
        for key in ('start', 'end'):
            if value[key] is not None:
                if value['kind'] == 'partial' and value['precision'] == 'day' and isinstance(value[key],str) and len(value[key]) == 10:
                    date.fromisoformat(value[key])
                else:
                    timestamp(value[key])
        kind, lower, upper = value['kind'], value['start'], value['end']
        if kind in {'point','approximate','after'} and (lower is None or upper is not None):
            raise ValueError('Time kind requires a start and no end')
        if kind == 'before' and (lower is not None or upper is None):
            raise ValueError('Before requires only an upper bound')
        if kind == 'interval' and (lower is None or upper is None):
            raise ValueError('Interval requires both endpoints')
        if value['start'] is not None and value['end'] is not None and timestamp(value['start']) > timestamp(value['end']):
            raise ValueError('Time interval ends before its start')
        if value['kind'] != 'point' or value['precision'] not in {'second', 'minute'}:
            result['status'] = 'UNCERTAIN'
            return result
        if value['end'] is not None:
            raise ValueError('Point LKW cannot have an end')
        value = value['start']
    start = timestamp(value)
    if start > view.now:
        raise ValueError('LKW cannot be later than evaluated_at')
    elapsed = (view.now - start).total_seconds()
    result.update(status='WITHIN_STANDARD_WINDOW' if elapsed <= policy.standard_window_seconds else 'STANDARD_WINDOW_ELAPSED',
                  elapsed_seconds=elapsed, deadline=(start + timedelta(seconds=policy.standard_window_seconds)).isoformat(),
                  remaining_seconds=max(0, policy.standard_window_seconds - elapsed))
    return result
