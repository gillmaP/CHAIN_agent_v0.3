"""Validated weight-entry adapter. Persistence, authentication and routing belong to Host."""
from .facts import number, timestamp, Facts
from .dose import preview
from .policy import POLICY

METHODS = {'MEASURED','PATIENT_REPORTED','CAREGIVER_REPORTED','ESTIMATED'}


def weight_facts(weight_kg, *, method, staff_id, entry_id, version, recorded_at):
    number(weight_kg, 'weight_kg')
    if weight_kg <= 0 or method not in METHODS:
        raise ValueError('Positive weight and explicit measurement/reporting method required')
    if not all(isinstance(x,str) and x.strip() for x in (staff_id,entry_id)):
        raise ValueError('Weight entry identity is required')
    if type(version) is not int or version < 1:
        raise ValueError('Weight entry version must be a positive integer')
    timestamp(recorded_at)
    result = {}
    for name, value in (('weight_kg',weight_kg),('weight_method',method),('weight_entered_by',staff_id)):
        result[name] = {'value':value,'status':'AVAILABLE',
            'source_ref':{'system':'MANUAL_WEIGHT','record_id':entry_id,'version':version,'field':name},
            'source_time':recorded_at,'known_at':recorded_at}
    result['weight_kg']['unit'] = 'kg'
    return result


def weight_preview(weight_kg, *, method, staff_id, entry_id, version, recorded_at, policy=POLICY):
    facts = weight_facts(weight_kg,method=method,staff_id=staff_id,entry_id=entry_id,version=version,recorded_at=recorded_at)
    return preview(Facts(facts,recorded_at,recorded_at),policy)
