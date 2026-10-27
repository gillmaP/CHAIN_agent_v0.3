"""Explicit A02-to-Fact mapping. A Host must pin the summary's cutoff and identity."""
import copy
from ..common import canonical_hash
from .facts import timestamp

FIELDS = {'anticoagulant_use':'anticoagulant', 'antiplatelet_use':'antiplatelet',
          'recent_surgery':'recent_surgery', 'recent_bleeding':'recent_bleeding',
          'previous_stroke':'previous_stroke', 'lkw_records':'lkw'}
STATUSES = {'documented':'AVAILABLE', 'not_stated':'NO_EVIDENCE',
            'explicitly_unknown':'UNKNOWN', 'conflicting':'CONFLICT', 'not_applicable':'UNKNOWN'}


def summary_facts(summary, *, episode_id, encounter_id, source_ref, source_time, known_at):
    if summary.get('schema_version') != 'summary-items/v1':
        raise ValueError('Unsupported Summary schema')
    if (summary.get('episode_id'), summary.get('encounter_id')) != (episode_id, encounter_id):
        raise ValueError('Summary episode/encounter mismatch')
    if timestamp(source_time) > timestamp(known_at):
        raise ValueError('Summary source time is after known_at')
    if (not isinstance(source_ref, dict) or set(source_ref) != {'system','record_id','version'}
            or not all(isinstance(source_ref.get(k),str) and source_ref[k].strip() for k in ('system','record_id'))
            or type(source_ref.get('version')) is not int or source_ref['version'] < 1):
        raise ValueError('Host must supply the versioned Summary source reference')
    items = summary.get('items')
    if not isinstance(items, list):
        raise ValueError('Summary items must be a list')
    result = {}
    for item in items:
        if not isinstance(item,dict) or set(item) != {'question','status','value','evidence','alternatives'}:
            raise ValueError('Invalid Summary item shape')
        question, status = item.get('question'), item.get('status')
        if question not in FIELDS or status not in STATUSES or FIELDS[question] in result:
            raise ValueError('Unknown/duplicate Summary question or status')
        value = item.get('value')
        evidence, alternatives = item['evidence'], item['alternatives']
        if not isinstance(evidence,list) or not isinstance(alternatives,list):
            raise ValueError('Summary evidence and alternatives must be arrays')
        if status in {'documented','explicitly_unknown'} and (not evidence or alternatives):
            raise ValueError('Documented/unknown statements require their evidence')
        if status == 'not_stated' and (evidence or alternatives):
            raise ValueError('Not-stated answers cannot invent evidence')
        if status == 'conflicting' and (evidence or len(alternatives) < 2):
            raise ValueError('Conflicts require separate candidates')
        if status == 'documented' and (not isinstance(value, dict) if question == 'lkw_records' else type(value) is not bool):
            raise ValueError('Summary answer has wrong value type')
        if status != 'documented' and value is not None:
            raise ValueError('Unknown Summary answer must remain null')
        name = FIELDS[question]
        result[name] = {'value':copy.deepcopy(value), 'status':STATUSES[status],
                        'source_ref':{**copy.deepcopy(source_ref),'field':name},
                        'source_time':source_time, 'known_at':known_at,
                        'confirmation_status':'UNCONFIRMED'}
    # Keep quotes/alternatives in a separate scoped Fact, without adding wire metadata.
    result['summary_evidence'] = {'value':copy.deepcopy(items), 'status':'AVAILABLE',
        'source_ref':{**copy.deepcopy(source_ref),'field':'summary_evidence'},
        'source_time':source_time, 'known_at':known_at}
    return result


def _equivalent(name, left, right):
    if left == right:
        return True
    if name != 'lkw':
        return False
    def point(value):
        if isinstance(value, str):
            return timestamp(value)
        if isinstance(value, dict) and value.get('kind') == 'point' and value.get('precision') in {'second','minute'} and value.get('end') is None:
            return timestamp(value.get('start'))
        return None
    a, b = point(left), point(right)
    return a is not None and a == b


def merge_summary(snapshot, mapped):
    """Merge only absent/unknown data. Preserve differing available observations."""
    result = copy.deepcopy(snapshot)
    for name, incoming in mapped.items():
        existing = result['facts'].get(name)
        if existing and existing['value'] is not None and existing['status'] in {'AVAILABLE','CONFIRMED','COMPLETED','PRESENT','CONSISTENT'}:
            if incoming['status'] == 'AVAILABLE' and not _equivalent(name, incoming['value'], existing['value']):
                result['facts'][name] = {'value':None, 'status':'CONFLICT',
                    'source_ref':copy.deepcopy(incoming['source_ref']),
                    'source_time':incoming['source_time'], 'known_at':incoming['known_at'],
                    'dependencies':copy.deepcopy(existing.get('dependencies',[existing['source_ref']]) +
                                                 incoming.get('dependencies',[incoming['source_ref']]))}
                result['facts'][name + '_alternatives'] = {'value':[copy.deepcopy(existing),copy.deepcopy(incoming)],
                    'status':'AVAILABLE', 'source_ref':{**copy.deepcopy(incoming['source_ref']),'field':name+'_alternatives'},
                    'source_time':incoming['source_time'],'known_at':incoming['known_at']}
            continue
        result['facts'][name] = copy.deepcopy(incoming)
    result['known_at'] = max([snapshot['known_at']] + [f['known_at'] for f in mapped.values()], key=timestamp)
    result['snapshot_id'] = canonical_hash({k:v for k,v in result.items() if k != 'snapshot_id'})
    return result
