"""Source-based review of every gold field, frozen before rerunning models."""
import json
from pathlib import Path

PRIOR_ROOT = Path('/data/data2/jhbak/CHAIN_agent_summary_prototype/outputs/summary_s1_single_call_order_20261008_v1')
REASONS = {
    '01_positive_use': [
        '현재 항응고제 복용을 명시한다.', '현재 항혈소판제 복용을 명시한다.',
        '최근 6개월 수술과 출혈 모두 없었다는 명시적 부정이다.', '같은 문장이 출혈도 명시적으로 부정한다.',
        '환자 본인의 2021년 뇌졸중 병력을 명시한다.', '두 문서 모두 2026-10-08 09:10 LKW에 동의한다. 10:00은 발견 시각이다.',
    ],
    '02_explicit_unknown': [
        '복용 여부를 모르며 확인 불가라고 명시한다.', '복용 여부를 모른다고 명시한다.',
        '최근 수술 여부를 확인할 수 없다고 명시한다.', '최근 출혈 여부도 확인할 수 없다고 명시한다.',
        '과거 병력 여부를 알 수 없다고 명시한다.', '환자와 보호자 모두 LKW를 모른다고 명시한다.',
    ],
    '03_family_current': [
        '환자 현재 복용을 명시적으로 부정한다.', '환자 현재 복용을 명시적으로 부정한다.',
        '최근 수술을 명시적으로 부정한다.', '최근 출혈을 명시적으로 부정한다.',
        '미문진을 명시하므로 explicitly_unknown/null이다. 아버지 병력이나 현재 의심 진단은 환자 과거력의 긍정·부정 근거가 아니다. 기존 not_stated GT를 수정한다.',
        '06:00이 LKW이며 minute 정밀도이다. 07:30은 발견 시각으로 별개다.',
    ],
    '04_conflicting_sources': [
        '같은 현재 복용 여부에 환자 true와 보호자 false가 상충한다. 두 후보와 출처를 보존한다.',
        '첫 문서가 항혈소판제 복용을 명시적으로 부정한다.', '첫 문서가 최근 수술을 부정한다.',
        '첫 문서가 최근 출혈을 부정한다.', '첫 문서가 과거 뇌졸중 병력을 부정한다.',
        '같은 사건의 LKW가 09:10과 09:40으로 상충한다. 한쪽 시각을 택하면 안 된다.',
    ],
    '05_external_vs_local': [
        '타원 rivaroxaban 현재 복용을 명시한다. 본원 목록이 비었다는 것은 부정 근거가 아니다.',
        '현재 항혈소판제 복용을 명시적으로 부정한다.', '2주 전 타원 수술을 명시한다.',
        '제공된 문서에서 출혈에 관한 진술이 없다. 로컬 내원 한 건의 출혈 false는 전체 기간의 부정이 아니다. not_stated를 유지한다.',
        '과거 뇌졸중이나 TIA 없었다고 명시한다. 현재 잠정 진단은 과거력이 아니다.', '문서 날짜 기준 오늘 11:45가 LKW이다.',
    ],
    '06_partial_negation': [
        '현재 항응고제 비복용을 명시한다.', '현재 항혈소판제 비복용을 명시한다.',
        '최근 수술 없음을 명시한다.', '출혈 여부 미문진을 명시한다. explicitly_unknown/null이며 false가 아니다.',
        '과거 뇌졸중 병력 없음을 명시한다.', '15시쯤이라는 유용한 근삿값이 존재한다. approximate/hour를 보존하고 정확한 분·초를 추정하지 않는다.',
    ],
    '07_silent_records': [
        '관련 질문에 관한 언급이 전혀 없다. 증상·활력징후·검사 준비만으로 답을 추정하지 않는다.'
    ] * 6,
    '08_alias_midnight': [
        '현재 항응고제 비복용을 명시한다.', 'ASA/아스피린 항혈소판제 현재 복용을 명시한다.',
        '최근 수술은 없었지만 어제 출혈이 있었다에서 수술은 false이다. 인용을 없었다로 고쳐 쓰면 원문 일치 실패이며 GT 문제가 아니다.',
        '어제 출혈이 있었다고 명시한다.', '질문 범위가 과거 stroke 또는 TIA이므로 2017년 TIA는 true이다.',
        '전날 23:50과 명시된 2026-10-07 23:50은 같은 LKW이다. 다음날 00:20은 발견 시각이다.',
    ],
}


def build_audit(dataset):
    old_cases = {c['case_id']: c for c in json.loads((PRIOR_ROOT / 'cases.json').read_text())}
    rows, changes = [], []
    for case in dataset:
        old = old_cases[case['case_id']]
        assert old['request'] == case['request'] and old['api_responses'] == case['api_responses']
        assert len(REASONS[case['case_id']]) == len(case['gold_items']) == 6
        for before, after, reason in zip(old['gold_items'], case['gold_items'], REASONS[case['case_id']]):
            row = {'case_id': case['case_id'], 'question': after['question'],
                   'decision': 'corrected' if before != after else 'retained',
                   'reason': reason, 'previous_GT': before, 'reviewed_GT': after}
            rows.append(row)
            if before != after:
                changes.append(row)
    assert len(rows) == 48 and len(changes) == 1
    assert changes[0]['case_id'] == '03_family_current' and changes[0]['question'] == 'previous_stroke'
    prior_evaluation = json.loads((PRIOR_ROOT / 'evaluation.json').read_text())
    both_wrong = []
    for method, models in prior_evaluation.items():
        for case in dataset:
            cid = case['case_id']
            for gt in case['gold_items']:
                q = gt['question']
                left = models['qwen35_9b']['cases'][cid]['field_rows'][q]
                right = models['gemma4_12b_it']['cases'][cid]['field_rows'][q]
                if not left['exact'] and not right['exact']:
                    review = next(r for r in rows if r['case_id'] == cid and r['question'] == q)
                    both_wrong.append({'method': method, 'case_id': cid, 'question': q,
                        'GT_decision': review['decision'], 'source_based_reason': review['reason'],
                        'qwen_final': left['actual'], 'gemma_final': right['actual'],
                        'includes_case_rejection': left['actual'] is None or right['actual'] is None})
    return {'review_version': 's1-gold-review-v2', 'reviewed_fields': 48,
        'changed_fields': 1, 'input_documents_unchanged': True,
        'review_basis': 'Read all supplied synthetic source documents and structured records; apply the same information-status rule to every question. Agent review, not clinician adjudication.',
        'status_examples': {
            'explicit_denial': {'status': 'documented', 'value': False},
            'explicit_nonassessment_or_unknown': {'status': 'explicitly_unknown', 'value': None},
            'no_relevant_statement': {'status': 'not_stated', 'value': None},
        },
        'other_corrections': [
            'Accept full not_stated/null/empty-evidence candidates as valid no-mention markers. Required keys remain required; supported facts take precedence.',
            'Medication value-schema wording now allows null for non-documented statuses, consistent with every other question.',
            'Missing keys and invalid verbatim quotes remain errors; no automatic semantic repair or GT-specific answers are inserted.',
        ],
        'prior_both_models_wrong': both_wrong, 'all_field_reviews': rows}
