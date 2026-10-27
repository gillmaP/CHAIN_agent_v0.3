# assessment prototype-v2 계약

공개 함수와 최상위 네 키는 유지합니다. assessment.schema가 chain-tpa-assessment/prototype-v2로 바뀌며 아래 필드를 추가합니다. v1 enum만 처리하는 UI는 공동 검토가 필요합니다.

| 필드 | 내용 |
|---|---|
| protocol, protocol_parameters | ID·버전·승인 선언 및 실제 전체 수치 설정 |
| stage | INTERIM_REVIEW / FINAL_REVIEW. 자료 완비나 CT 판독 완료를 보장하지 않음 |
| data_completeness | PARTIAL / AVAILABLE_FOR_REVIEW. 치료 적합성 아님 |
| time_window | status, evaluated_at, lkw, elapsed_seconds, deadline, remaining_seconds, basis, protocol ID/version |
| checks[].data_status | AVAILABLE, PENDING, NO_RECORD, UNKNOWN, NOT_IN_SCOPE, CONFLICT, UNAVAILABLE |
| checks[].clinical_result | CONDITION_MET, CONDITION_NOT_MET, REVIEW_REQUIRED, NOT_ASSESSED, INFO |
| checks[].display | data_label, result_label, priority |
| dose_preview.weight_method | MEASURED, PATIENT_REPORTED, CAREGIVER_REPORTED, ESTIMATED, UNKNOWN |
| dose_preview.protocol, calculator_version | 계산 설정과 코드 버전 |

실제 출력은 `python -m chain_agents.tpa.demo final`로 JSON 전체를 재현합니다. 아래는 검사 대기 항목의 일부 필드 예시입니다.

```json
{
  "check_id": "C04_INR_LE_1_7",
  "result": "PENDING",
  "value": null,
  "data_status": "PENDING",
  "clinical_result": "NOT_ASSESSED",
  "display": {"data_label": "대기", "result_label": "평가 전", "priority": 2}
}
```

기존 label, detail, evidence, source_ids도 유지합니다. evidence는 환자 Fact의 값 이외 metadata를 보존하며 원래 값은 evidence_package에 있습니다. 문헌 ID와 환자 출처를 구별합니다. 추가 scope가 있으면 12개보다 많은 check를 반환하므로 UI에서 개수를 고정하면 안 됩니다.

CONDITION_MET는 site-approved 설정의 일부 수치 FAIL에만 사용합니다. CONDITION_NOT_MET는 해당 수치 조건에만 사용하며 전체 금기 없음을 의미하지 않습니다. 연구 기본값은 FAIL도 REVIEW_REQUIRED로 표시합니다. priority는 조건 해당(0), 검토 필요(1), 평가 전(2), 참고(3), 해당 조건 비해당(4)입니다. 임상 화면 정렬은 JLK/의료진과 확정해야 합니다.

기존 aggregate status는 BLOCKING_FINDING_IDENTIFIED / INCOMPLETE_PENDING_DATA / PHYSICIAN_REVIEW_REQUIRED를 호환용으로 유지합니다. **전체 치료 가능/불가나 HITL gate로 사용하지 않습니다.** mock_only=true, recommendation_type=DECISION_SUPPORT_ONLY, physician_decision_required=true입니다.

시간 status는 WITHIN_STANDARD_WINDOW / STANDARD_WINDOW_ELAPSED / UNCERTAIN / UNKNOWN입니다. 부정확한 시각의 deadline/remaining은 null입니다. 기준은 evaluated_at이며 실행 환경의 현재 시각을 몰래 읽지 않습니다.

용량은 약제 선택·치료 결정과 독립된 kg 산술입니다. Decimal 원값과 표시용 반올림 값을 구별합니다. auto_order=false, auto_administration=false, physician_confirmation_required=true를 유지합니다. 기관 약제 채택·반올림·조제·투여 방식 검증은 별도입니다.

Host 공통 envelope의 SUCCESS는 Agent 실행 성공입니다. reference adapter의 snapshot.tpa_execution[mode]는 RUNNING / SUCCESS / FAILED와 request_id, input_snapshot_id, error를 제공합니다. FAILED에는 timeout, 오류, 늦거나 검증에 실패해 수락하지 않은 결과도 포함합니다. 의료진은 fixed HITL evidence를 기준으로 판단합니다.
