"""UI projection keeps data availability separate from protocol interpretation."""
DATA_LABELS = {'AVAILABLE':'확보', 'PENDING':'대기', 'NO_RECORD':'기록 없음',
               'UNKNOWN':'미확인', 'NOT_IN_SCOPE':'범위 밖', 'CONFLICT':'출처 충돌', 'UNAVAILABLE':'사용 불가'}
RESULT_LABELS = {'CONDITION_MET':'프로토콜 조건 해당', 'CONDITION_NOT_MET':'해당 조건 비해당',
                 'REVIEW_REQUIRED':'의료진 확인 필요', 'NOT_ASSESSED':'평가 전', 'INFO':'참고 정보'}


def data_status(evidence):
    if not evidence:
        return 'NOT_IN_SCOPE'
    statuses = {item['status'] for item in evidence}
    for status in ('CONFLICT', 'ERROR', 'RETRACTED', 'INVALIDATED', 'UNAVAILABLE', 'PENDING', 'NO_EVIDENCE', 'UNKNOWN'):
        if status in statuses:
            return {'ERROR':'UNAVAILABLE', 'RETRACTED':'UNAVAILABLE', 'INVALIDATED':'UNAVAILABLE',
                    'NO_EVIDENCE':'NO_RECORD'}.get(status, status)
    return 'AVAILABLE' if statuses <= {'AVAILABLE','CONFIRMED','CONSISTENT','PRESENT','COMPLETED'} else 'UNKNOWN'


def decorate(checks, policy):
    for item in checks:
        availability = data_status(item['evidence'])
        result = item['result']
        if availability == 'AVAILABLE' and result == 'PENDING':
            availability = 'UNKNOWN'
        clinical = ('NOT_ASSESSED' if result in {'PENDING','NOT_IN_SCOPE'} else
                    'INFO' if result == 'INFO' else
                    'CONDITION_MET' if result == 'FAIL' and policy.approval_status == 'SITE_APPROVED' else
                    'CONDITION_NOT_MET' if result == 'PASS' and policy.approval_status == 'SITE_APPROVED'
                       and item['check_id'] in {'C03_PLATELET_GE_100K','C04_INR_LE_1_7','C06_BP_LT_185_110','C07_GLUCOSE_50_400'} else
                    'REVIEW_REQUIRED')
        item.update(data_status=availability, clinical_result=clinical,
                    display={'data_label': DATA_LABELS[availability], 'result_label': RESULT_LABELS[clinical],
                             'priority': {'CONDITION_MET':0,'REVIEW_REQUIRED':1,'NOT_ASSESSED':2,'INFO':3,'CONDITION_NOT_MET':4}[clinical]})
    return checks
