# 구조화된 assessment 제안

브랜치 `feature/tpa-rules`, schema 식별자 `chain-tpa-assessment/prototype-v1`.
최상위 도메인 키와 공개 함수는 유지하며, `assessment` 값의 타입만 확장합니다.
기존 문자열 타입을 사용하는 소비자와의 공동 검토가 필요합니다.

```text
mode: interim | final
evidence_package: 원본 scoped Fact dict의 독립적인 복사본
mock_only: true
assessment:
  schema, rule_set: 제안 schema와 연구 규칙 버전
  status: 아래 3가지 검토 상태
  checks: 12개 check_id, label, result, value, detail, evidence, source_ids
  missing_information: 기본 필수 Fact 중 미확보 항목
  scope_gaps: NOT_IN_SCOPE 체크 ID
  items_requiring_physician_confirmation: 확인 대상 체크 ID
  dose_preview: 체중, 계산 options, 출처, 산술 기준, 자동 처방/투약 금지
  limitations: 연구 범위와 미확정 임상 사항
  recommendation_type: DECISION_SUPPORT_ONLY
  physician_decision_required: true
```

## status

| 상태 | 의미 |
|---|---|
| `BLOCKING_FINDING_IDENTIFIED` | 제공된 검사에서 연구 임계값 밖의 소견 발견. 전체 금기 판정은 아님 |
| `INCOMPLETE_PENDING_DATA` | 필수 Fact가 미확보이거나 NCCT가 완료되지 않음 |
| `PHYSICIAN_REVIEW_REQUIRED` | 충돌 또는 확보된 자료의 의료진 평가 필요 |

FAIL 소견, CONFLICT, 필수 자료 미확보 순으로 상태를 정합니다.
값이 false/0인 것과 null을 구분하며, 정상 데이터 완비를 치료 적합성으로 표현하지 않습니다.
검사 미확보 표시는 검사 대기로 치료를 지연하라는 지시가 아닙니다.

## checks

`PASS`, `INFO`는 해당 자료/산술 체크만 설명합니다. `FAIL`은 제공된 검사 소견입니다.
`PENDING`, `CONFLICT`, `NOT_IN_SCOPE`, `PASS_UNCONFIRMED`, `PASS_WITH_FLAG`,
`REQUIRES_PHYSICIAN_READ`, `REQUIRES_PHYSICIAN_REVIEW`는 미확정 근거를 구분합니다.
사용 가능한 Fact 상태는 AVAILABLE/CONFIRMED/CONSISTENT/PRESENT이며,
그 외 상태는 원문을 evidence_package에 유지하고 미확보로 표시합니다.

각 체크의 `evidence`는 요청 scope 안의 Fact metadata입니다. source_ref, version,
source_time, known_at, unit, confirmation_status, dependencies를 유지합니다.
파생 Fact의 원본 dependencies도 보존합니다. 없는 Fact의 근거는 빈 배열입니다.
문헌 출처 source_ids는 환자 근거와 별도로 SOURCES.md에 매핑합니다.

## 용량 preview

`assessment.dose_preview` 안에만 있습니다. 최상위 출력 key를 추가하지 않습니다.
체중의 필드 계약은 kg이며, 충돌하는 명시적 단위는 오류입니다.
임상 적합성·병원 약제 승인 확인과 독립적인 산술 예시입니다.
`auto_order=false`, `auto_administration=false`, `physician_confirmation_required=true`입니다.

## 통합 시 확인

1. Console의 문자열 assessment 렌더링과 새 객체·enum 처리.
2. 추가 병력 Fact 이름, scope, confirmation_status 용어.
3. 기관 승인 프로토콜, 약제와 자료 단위 규약.
4. Agent 버전과 파일 hash를 포함한 Registry 검토·갱신.

이 변경은 Clinical Summary equality, 이벤트, 상태전이, HITL 조건, 공통 wire validator를 변경하지 않습니다.
