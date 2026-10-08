# Summary 입출력 계약

실행과 모듈 연결 방법은 [README.md](README.md)를 참고하세요.
Summary는 한 번 호출해 전체 질문 결과를 반환합니다. 결과 형식 이름은 `summary-items/v1`입니다.

## 1. 요청

| 필드 | 규칙 |
|---|---|
| `patient_id`, `encounter_id`, `episode_id` | 비어 있지 않은 문자열 |
| `input_references` | 중복 없는 지원 참조 목록. 모든 요청 자료가 필수 |
| `questions` | 지원하는 질문 ID 목록. 자유 자연어 질문 미지원 |

자료를 조회한 뒤 환자 ID를 검증합니다. 문서는 참조의 문서 ID·버전, 내원 ID, 문서 유형과 상태를 검증합니다.
문서 유형은 `ED_INITIAL_NOTE` 또는 `ED_TRIAGE_NOTE`, 상태는 `CURRENT` 또는 `SUPERSEDED`를 허용하며 지정 버전을 사용합니다.

## 2. 질문과 값

| Question ID | `documented`일 때 value | 범위 |
|---|---|---|
| `anticoagulant_use` | Boolean | 환자 본인의 현재 항응고제 복용 여부 |
| `antiplatelet_use` | Boolean | 환자 본인의 현재 항혈소판제 복용 여부 |
| `recent_surgery` | Boolean | 제공된 최근 병력 범위의 수술 여부 |
| `recent_bleeding` | Boolean | 제공된 최근 병력 범위의 출혈 여부 |
| `previous_stroke` | Boolean | 환자 본인의 과거 뇌졸중/TIA. 가족력·현재 의심 사건 제외 |
| `lkw_records` | 시간 객체 | 이번 사건의 마지막 정상 확인 시각. 증상 발생·발견·기록 작성 시각과 구분 |

- `recent_surgery_or_bleeding` → `recent_surgery`, `recent_bleeding`으로 확장합니다.
- `anticoagulant_use` 요청에 `antiplatelet_use`를 자동 포함합니다.
- 중복을 제거하고 위 catalog 순서로 반환합니다.
- 최근 병력의 기본 검색 범위는 6개월입니다. 특정 치료의 금기 기간을 판정하는 규칙은 아닙니다.
- Boolean 값은 JSON `true`/`false`입니다. 약명·용량은 근거에 보존하며 Boolean 자리에 문자열을 넣지 않습니다.
- 목록에 약물·질환이 없다는 사실만으로 `false`를 만들지 않습니다.

## 3. 내부 전체 결과

Agent 반환 dict는 다음 필드를 가집니다.

| 필드 | 내용 |
|---|---|
| `schema_version` | `summary-items/v1` |
| `episode_id`, `encounter_id` | 요청의 식별자 |
| `input_references` | 요청한 자료 참조 |
| `questions` | 정규화된 실제 처리 질문 |
| `items` | 질문마다 하나의 최종 항목 |
| `missing_information` | 미기록·미확인·상충과 자료 범위 한계 |
| `model_info` | 규칙 버전, 모델 key, 추출 방식 등 |
| `mock_only` | 합성 자료 여부 |

모든 최종 item은 `question`, `status`, `value`, `evidence`, `alternatives` 다섯 필드를 가집니다.

```json
{
  "question": "anticoagulant_use",
  "status": "documented",
  "value": false,
  "evidence": [
    {"source_ref": "document:NOTE-example@1", "quote": "현재 항응고제를 복용하지 않는다"}
  ],
  "alternatives": []
}
```

### 상태

| status | 의미 | value | evidence / alternatives |
|---|---|---|---|
| `documented` | 원문에 답이 있음. 명시적 부정도 여기에 해당 | 질문 타입의 실제값 | 근거 필수 / 빈 alternatives |
| `not_stated` | 검토한 입력에 언급 없음 | `null` | 모두 빈 배열 |
| `explicitly_unknown` | 모름·확인 불가·미문진·미평가 명시 | `null` | 해당 진술의 근거 필수 |
| `conflicting` | 동일 대상·질문·시간 범위에 상충하는 값 | `null` | 부모 evidence는 빈 배열, alternatives에 서로 다른 값과 근거 |
| `not_applicable` | 합의된 적용 규칙상 해당 없음 | `null` | 예약 상태. 현재 여섯 질문에서는 생성하지 않음 |

“과거 뇌졸중 병력을 문진하지 않았다”는 `explicitly_unknown/null`입니다. “과거 뇌졸중 병력이 없다”는 `documented/false`입니다.
`not_stated` 표시는 근거가 있는 진술을 덮어쓰지 않습니다. 상충은 코드가 후보들을 결합하며 보존합니다.
자료 API 실패는 임상 status가 아닌 실행 실패입니다.

### 시간 객체

LKW의 documented 값은 `kind`, `start`, `end`, `precision`, `original_text` 다섯 필드를 가집니다.

| kind | start | end |
|---|---|---|
| `point` | 단일 시각 | `null` |
| `approximate` | 근사 시각 | `null` |
| `interval` | 구간 시작 | 구간 끝 |
| `before` | `null` | 상한 시각 |
| `after` | 하한 시각 | `null` |
| `partial` | 날짜만 있으면 `YYYY-MM-DD`; 정규화 불가하면 `null` | `null` |

`precision`: `second`, `minute`, `hour`, `day`, `unknown`.
날짜·시각은 timezone을 포함하며 한국 현지 시각은 `YYYY-MM-DDTHH:MM:SS+09:00`으로 씁니다.
분 단위 기록의 초를 `:00`으로 표기해도 `precision:minute`을 유지합니다.
날짜만 있으면 `precision:day`, 두 끝점 모두 알 수 없는 partial은 `precision:unknown`입니다.
`original_text`에는 근사 표현을 포함한 원문을 보존합니다. 치료 가능 시간이나 적격성을 계산하지 않습니다.

### 근거와 상충

- 문서 근거: `{source_ref, quote}`. 여러 문장·문서가 필요하면 여러 evidence 항목으로 보존합니다.
- 구조화 근거: `{source_ref, record}`. 원본 자료의 해당 레코드를 보존합니다.
- 인용 검증은 Unicode NFKC·대소문자·공백을 정규화한 부분문자열 비교입니다.
  원문에 존재하는지는 검사하지만 그 인용이 답의 의미를 실제로 뒷받침하는지까지 증명하지는 않습니다.
- 상충은 `alternatives: [{value, evidence}, ...]`에 보존하고 모델이 임의로 하나를 선택하지 않습니다.

## 4. LLM과 코드의 경계

LLM 입력은 질문 catalog와 지정 문서입니다. API token이나 실행 저장소는 전달하지 않습니다.
모델 출력은 `facts`와 `reviewed_documents`이며 각 fact는 `question`, `status`, `value`, `evidence`를 가집니다.
코드는 필드·질문·타입·시간 형식·출처·인용·전체 문서 검토 여부를 검증한 뒤 구조화 자료와 결합합니다.
최종 `alternatives`와 미기록 상태는 코드에서 정리합니다.

모델은 한 번 호출합니다. 기본은 `direct`이며 `evidence_first`는 생성 순서 비교 옵션입니다.
둘 다 별도 인용 추출 단계나 두 번째 모델 호출을 사용하지 않습니다.

## 5. Orchestrator와의 경계

Summary는 질문별 임상 정보와 근거만 반환합니다. Orchestrator/Host는 Agent 선택, 실행 성공·실패 상태, 결과 저장, 화면 조회, 재시도와 workflow 전이를 관리합니다. API 경로 또는 등록 정보가 Summary를 선택하므로 임상 요청 본문에 `agent`나 `action`을 중복해서 넣지 않습니다.

`snapshot`이 제공되면 요청에 함께 전달된 `input_snapshot_id`와 일치하는지 확인합니다. Summary의 원문·구조화 자료는 `input_references`를 따라 `data_api`에서 조회합니다. 입력 자료 조회는 원천 시스템의 원자적 snapshot이나 과거 as-of 조회를 보장하지 않습니다. Host가 자료의 권한과 기준 시점을 보장해야 합니다.

## 6. 입력 감사 정보

선택적인 `input_observer` 콜백은 추론 전에 확보한 원본 자료 `resources`와 감사 정보 `metadata`를 받습니다.
자료 조회 실패 시에는 확보한 범위까지 전달됩니다. 저장은 호출자가 수행하며 이 모듈은 DB를 만들지 않습니다.
자료별 해시·버전·조회 시각과 질문 정규화 내역을 포함합니다. `coverage:complete`는 요청 자료의
조회·검증 완료이며 병원 전체 자료 확보를 뜻하지 않습니다. 순차 조회는 원천 시스템의 원자적 snapshot이
아니며, 과거 as-of 조회를 보장하지 않습니다. Runtime이 사용할 시점과 접근 범위를 보장해야 합니다.

현재 여섯 질문만으로 치료 적격성을 판단하지 않습니다.
