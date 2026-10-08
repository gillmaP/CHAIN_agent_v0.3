from __future__ import annotations

import statistics
import time
from datetime import datetime, timezone

from .prototype import screen_documents


def synthetic_cases():
    cases = [
        ('01_acute_motor', '2026-10-08 10:00까지 정상, 10:20에 갑자기 우측 팔에 힘이 빠졌다.', 'POSITIVE'),
        ('02_acute_speech', '마지막 정상 확인 09:10. 09:30 급격히 실어증이 발생하고 발음이 어눌해졌다.', 'POSITIVE'),
        ('03_clear_normal_exam', '신경학적 국소 결손은 없다고 명시적으로 확인하였다.', 'NEGATIVE'),
        ('04_no_neuro_info', '복통으로 내원. 활력징후 혈압 130/80, 맥박 80.', 'REVIEW_REQUIRED'),
        ('05_family_history_only', '아버지는 2022년 뇌졸중 병력이 있다. 환자의 현재 신경학적 진찰은 미시행.', 'REVIEW_REQUIRED'),
        ('06_deficit_without_onset', '현재 좌측 팔다리 근력 약화 관찰. 언제부터인지는 미확인.', 'REVIEW_REQUIRED'),
        ('07_unknown_exam', '마지막 정상 시간 확인 불가. 신경학적 검사는 환자 협조 불가로 평가하지 못함.', 'REVIEW_REQUIRED'),
        ('08_acute_visual', '07:30까지 증상 없었고 08:00부터 갑자기 한쪽 시야가 보이지 않음.', 'POSITIVE'),
    ]
    return [{
        'case_id': cid, 'documents': [{
            'document_id': 'SYN-'+cid, 'version': 1,
            'document_type': 'ED_INITIAL_NOTE',
            'saved_time': '2026-10-08T12:00:00+09:00', 'text': note,
        }], 'expected_result': expected,
    } for cid,note,expected in cases]


def evaluate(model, cases=None):
    cases = cases if cases is not None else synthetic_cases()
    rows = []
    for case in cases:
        start = time.perf_counter()
        try:
            predicted = screen_documents(model, case['documents'])
            prediction = predicted['screening_result']
            error = None
            evidence = len(predicted['evidence'])
        except Exception as exc:
            prediction, evidence = None, 0
            error = f'{type(exc).__name__}: {str(exc)[:150]}'
        rows.append({
            'case_id': case['case_id'], 'ground_truth': case['expected_result'],
            'predicted': prediction, 'correct': prediction == case['expected_result'],
            'evidence_count': evidence, 'error': error,
            'runtime_seconds': round(time.perf_counter()-start, 3),
        })
    n = len(rows)
    valid = [row for row in rows if row['predicted'] is not None]
    correct = [row for row in rows if row['correct']]
    return {
        'experiment': 'team1_screening_synthetic_8',
        'model_key': getattr(model, 'model_key', 'test-double'),
        'model_revision': getattr(model, 'model_revision', 'unverified'),
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'cases': n,
        'valid_output_rate': round(len(valid)/n,4) if n else None,
        'exact_label_accuracy_all_cases': round(len(correct)/n,4) if n else None,
        'median_case_seconds': round(statistics.median([r['runtime_seconds'] for r in rows]),3) if rows else None,
        'results': rows,
        'limitations': 'Hand-authored synthetic 8 cases; no clinical validation. '
                       'A validated quote may still be clinically misinterpreted. '
                       'Only the prototype screening gate is scored.',
    }
