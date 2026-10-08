"""Re-annotated S1 fields: one typed status/value answer per requested question."""
import copy
from .history_stress_cases import cases as legacy_cases
from .history_s1_contract import QUESTION_ORDER, canonical_questions, evidence_entry


def _field(question, status, value=None, evidence=None, alternatives=None):
    return {'question': question, 'status': status, 'value': value,
            'evidence': evidence or [], 'alternatives': alternatives or []}


def _e(cid, document_number, quote):
    return evidence_entry(f'document:{cid}-{document_number}@1', quote)


def _doc(cid, number, quote):
    return [_e(cid, number, quote)]


def _bool(question, value, cid, number, quote):
    return _field(question, 'documented', value, _doc(cid, number, quote))


def _unknown(question, cid, number, quote):
    return _field(question, 'explicitly_unknown', None, _doc(cid, number, quote))


def _missing(question):
    return _field(question, 'not_stated')


def _time(start, precision, original_text, kind='point', end=None):
    return {'kind': kind, 'start': start, 'end': end,
            'precision': precision, 'original_text': original_text}


def _lkw(start, cid, number, quote, original_text, precision='minute', kind='point', end=None):
    return _field('lkw_records', 'documented', _time(start, precision, original_text, kind, end), _doc(cid, number, quote))


def _conflict(question, alternatives):
    return _field(question, 'conflicting', None, [],
                  [{'value': value, 'evidence': evidence} for value, evidence in alternatives])


def _gold():
    q = '현재 항응고제와 항혈소판제는 각각 같은 Boolean 규칙을 사용한다. 수술과 출혈은 부분 누락을 표현할 수 있도록 분리한다. LKW의 근사값은 가능한 정밀도로 기록하며 exact 시각을 만들지 않는다.'
    return {
        '01_positive_use': ([
            _bool('anticoagulant_use', True, '01_positive_use', 1, '현재 항응고제 apixaban 5 mg bid를 복용 중이다'),
            _bool('antiplatelet_use', True, '01_positive_use', 1, '항혈소판제로 아스피린 100mg qd도 현재 복용한다'),
            _bool('recent_surgery', False, '01_positive_use', 1, '최근 6개월 수술과 출혈은 모두 없었다'),
            _bool('recent_bleeding', False, '01_positive_use', 1, '최근 6개월 수술과 출혈은 모두 없었다'),
            _bool('previous_stroke', True, '01_positive_use', 1, '환자는 2021년 뇌졸중 병력이 있다'),
            _field('lkw_records', 'documented', _time('2026-10-08T09:10:00+09:00', 'minute', '오늘 09:10'),
                   [_e('01_positive_use', 1, '마지막 정상 확인 시각은 오늘 09:10이다'),
                    _e('01_positive_use', 2, '마지막 정상 시각은 오늘 09:10이다')]),
        ], q),
        '02_explicit_unknown': ([
            _unknown('anticoagulant_use', '02_explicit_unknown', 1, '항응고제 복용 여부를 모르며 확인 불가하다'),
            _unknown('antiplatelet_use', '02_explicit_unknown', 1, '항혈소판제 복용 여부도 모른다'),
            _unknown('recent_surgery', '02_explicit_unknown', 1, '최근 수술이나 출혈이 있었는지는 확인할 수 없다'),
            _unknown('recent_bleeding', '02_explicit_unknown', 1, '최근 수술이나 출혈이 있었는지는 확인할 수 없다'),
            _unknown('previous_stroke', '02_explicit_unknown', 1, '과거 뇌졸중 병력 여부는 알 수 없다'),
            _unknown('lkw_records', '02_explicit_unknown', 1, '마지막 정상 시각은 환자와 보호자 모두 모른다'),
        ], q),
        '03_family_current': ([
            _bool('anticoagulant_use', False, '03_family_current', 1, '현재 항응고제와 항혈소판제는 모두 복용하지 않는다'),
            _bool('antiplatelet_use', False, '03_family_current', 1, '현재 항응고제와 항혈소판제는 모두 복용하지 않는다'),
            _bool('recent_surgery', False, '03_family_current', 1, '최근 수술 및 출혈은 모두 없었다'),
            _bool('recent_bleeding', False, '03_family_current', 1, '최근 수술 및 출혈은 모두 없었다'),
            _unknown('previous_stroke', '03_family_current', 1, '환자 개인의 과거 뇌졸중 병력은 이번 문진에서 다루지 않았다.'),
            _lkw('2026-10-08T06:00:00+09:00', '03_family_current', 1, '오늘 마지막 정상 확인은 06:00이고, 증상 발견은 07:30이다', '오늘 마지막 정상 확인은 06:00'),
        ], q + ' 가족력과 현재 의심 진단은 환자의 과거 뇌졸중 질문의 답이 아니다.'),
        '04_conflicting_sources': ([
            _conflict('anticoagulant_use', [
                (True, _doc('04_conflicting_sources', 1, '환자는 오늘도 항응고제 warfarin을 복용 중이라고 진술했다')),
                (False, _doc('04_conflicting_sources', 2, '보호자는 환자가 현재 항응고제를 전혀 복용하지 않는다고 진술한다')),
            ]),
            _bool('antiplatelet_use', False, '04_conflicting_sources', 1, '항혈소판제는 현재 복용하지 않는다고 한다'),
            _bool('recent_surgery', False, '04_conflicting_sources', 1, '최근 수술과 출혈은 모두 없었다'),
            _bool('recent_bleeding', False, '04_conflicting_sources', 1, '최근 수술과 출혈은 모두 없었다'),
            _bool('previous_stroke', False, '04_conflicting_sources', 1, '과거 뇌졸중 병력은 없다'),
            _conflict('lkw_records', [
                (_time('2026-10-08T09:10:00+09:00', 'minute', '오늘 09:10'), _doc('04_conflicting_sources', 1, '이번 사건의 마지막 정상 시각은 오늘 09:10이라고 환자가 말한다')),
                (_time('2026-10-08T09:40:00+09:00', 'minute', '오늘 09:40'), _doc('04_conflicting_sources', 2, '이번 사건의 마지막 정상 시각이 오늘 09:40이라고 진술한다')),
            ]),
        ], q + ' 동일 episode의 현재 복용 여부와 LKW 충돌은 후보 값과 각각의 근거를 보존한다.'),
        '05_external_vs_local': ([
            _bool('anticoagulant_use', True, '05_external_vs_local', 1, '현재 타원 처방 항응고제 rivaroxaban을 매일 복용 중이라고 환자와 딸이 확인했다'),
            _bool('antiplatelet_use', False, '05_external_vs_local', 1, '항혈소판제는 현재 복용하지 않는다'),
            _bool('recent_surgery', True, '05_external_vs_local', 1, '2주 전 타원에서 수술을 받았다고 한다'),
            _missing('recent_bleeding'),
            _bool('previous_stroke', False, '05_external_vs_local', 1, '과거 뇌졸중이나 TIA는 없었다'),
            _lkw('2026-10-08T11:45:00+09:00', '05_external_vs_local', 1, '마지막 정상 확인은 오늘 11:45이다', '오늘 11:45'),
        ], q + ' 본원 조회에 없다는 사실만으로 환자가 복용하지 않는다고 판단하지 않는다.'),
        '06_partial_negation': ([
            _bool('anticoagulant_use', False, '06_partial_negation', 1, '항응고제와 항혈소판제는 현재 모두 복용하지 않는다'),
            _bool('antiplatelet_use', False, '06_partial_negation', 1, '항응고제와 항혈소판제는 현재 모두 복용하지 않는다'),
            _bool('recent_surgery', False, '06_partial_negation', 1, '최근 수술은 없었다'),
            _unknown('recent_bleeding', '06_partial_negation', 1, '출혈 여부는 문진하지 않았다'),
            _bool('previous_stroke', False, '06_partial_negation', 1, '과거 뇌졸중 병력은 없다'),
            _lkw('2026-10-08T15:00:00+09:00', '06_partial_negation', 1, '마지막 정상은 오늘 15시쯤으로 추정되며 정확한 시각은 확인할 수 없다', '오늘 15시쯤', precision='hour', kind='approximate'),
        ], q + ' 정확한 시각을 모른다는 문장이 있어도 유용한 대략 시각이 기록되어 있으면 근삿값을 보존한다.'),
        '07_silent_records': ([
            _missing('anticoagulant_use'), _missing('antiplatelet_use'),
            _missing('recent_surgery'), _missing('recent_bleeding'),
            _missing('previous_stroke'), _missing('lkw_records'),
        ], q + ' 제공된 문서 모두 검토한 뒤 언급이 없는 질문은 not_stated다.'),
        '08_alias_midnight': ([
            _bool('anticoagulant_use', False, '08_alias_midnight', 1, '현재 항응고제는 복용하지 않는다'),
            _bool('antiplatelet_use', True, '08_alias_midnight', 1, '항혈소판제로 ASA(아스피린) 100mg을 1일 1회 복용한다'),
            _bool('recent_surgery', False, '08_alias_midnight', 1, '최근 수술은 없었지만 어제 출혈이 있었다'),
            _bool('recent_bleeding', True, '08_alias_midnight', 1, '어제 출혈이 있었다'),
            _bool('previous_stroke', True, '08_alias_midnight', 1, '환자 본인은 2017년 TIA 병력이 있다'),
            _field('lkw_records', 'documented', _time('2026-10-07T23:50:00+09:00', 'minute', '전날 23:50'),
                   [_e('08_alias_midnight', 1, '마지막 정상은 전날 23:50 딸과 전화통화할 때였다'),
                    _e('08_alias_midnight', 2, 'LKW는 2026-10-07 23:50으로 보호자에게 확인했다')]),
        ], q + ' ASA/아스피린은 항혈소판제다. 날짜 경계를 포함해 LKW를 정규화한다.'),
    }


def cases():
    annotations = _gold()
    source_cases = legacy_cases()
    output = []
    for source in source_cases:
        case = copy.deepcopy(source)
        if case['case_id'] not in annotations:
            raise ValueError(f'No revised GT for {case["case_id"]}')
        gold_items, note = annotations[case['case_id']]
        case['questions'] = canonical_questions(case['request']['questions'])
        case['gold_items'] = gold_items
        case['annotation_note'] = note
        if [x['question'] for x in gold_items] != case['questions']:
            raise ValueError(f'GT question order mismatch for {case["case_id"]}')
        case.pop('gold_facts', None)
        case.pop('gold_final', None)
        case.pop('oracle_result', None)
        output.append(case)
    return output
