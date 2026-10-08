# CHAIN 임상 지원 Agent

본 저장소는 뇌졸중 진료 지원을 위한 세 개의 독립적인 Agent 프로토타입을 제공합니다. 각 Agent는 지정된 업무의 입력을 받아 결과를 반환합니다. Agent 간 직접 호출이나 하나의 고정 임상 흐름은 구현하지 않았으며, 모든 출력은 의료진의 검토를 위한 참고 정보입니다.

## 목차

- [1. 전체 구조와 통일 범위](#1-전체-구조와-통일-범위)
- [2. Stroke Screening Agent](#2-stroke-screening-agent)
- [3. Clinical Summary Agent](#3-clinical-summary-agent)
- [4. tPA Decision Support Agent](#4-tpa-decision-support-agent)
- [5. Orchestrator 및 Tool/API 연동](#5-orchestrator-및-toolapi-연동)
- [6. 실행 방법](#6-실행-방법)
- [7. 향후 보완 사항](#7-향후-보완-사항)
- [8. 코드 구성](#8-코드-구성)

## 1. 전체 구조와 통일 범위

Orchestrator는 실행할 Agent를 선택하고, 해당 Agent에 필요한 입력을 준비해 호출합니다. Agent는 담당 업무만 수행한 뒤 업무 결과를 반환합니다.

세 Agent가 함께 사용하는 Python 진입점은 다음과 같습니다.

```python
invoke(request, snapshot, services) -> dict
```

**통일된 것은 진입 함수와 인자 전달 방식입니다.** 공통 입력 본문이나 공통 결과 스키마까지 통일된 것은 아닙니다. 각 Agent가 수행하는 업무와 사용하는 자료가 다르므로 `request`, `snapshot`, `services`의 실제 내용과 반환 결과는 Agent별로 다릅니다.

| Agent | `request` | `snapshot` | 주요 `services` | 반환 결과 |
|---|---|---|---|---|
| Screening | 요청 ID, 자료 범위, 평가 시각 | 범위에 포함된 원문 문서와 구조화 정보 | 합성 또는 로컬 LLM backend | 선별 결과와 근거 목록 |
| Summary | 환자·내원·에피소드 ID, 자료 참조, 질문 | 선택 사항. 원문과 구조화 자료는 주로 자료 참조로 조회 | 자료 조회기, 문서 추출기, 선택적 입력 감사기 | 질문별 상태·값·근거와 누락 정보 |
| tPA | 평가 단계, 범위, 평가 시각 | 범위에 포함된 구조화 임상 정보 | 현재 사용하지 않음 | 규칙별 평가, 누락 정보, 의료진 확인 항목 |

Agent 선택은 Orchestrator의 등록 정보 또는 라우팅 단계에서 처리합니다. 임상 요청 본문에 `agent`를 반복해서 넣지 않습니다. Summary는 한 번의 호출에서 요청된 질문을 모두 처리하므로 별도의 `action`을 요구하지 않습니다. tPA의 `mode`는 `interim`과 `final` 평가 단계를 구분하므로 입력에 포함합니다.

## 2. Stroke Screening Agent

### 목적과 처리

진료 문서에서 급성 발병, 국소 신경학적 증상 등 선별 근거를 추출하고, 코드의 프로토타입 규칙으로 결과를 정리합니다. 이 규칙은 검증된 진단 기준이 아닙니다.

LLM에는 범위가 지정된 `documents`와 별도 `structured_facts`가 전달되며, 문서에서 근거가 되는 진술을 추출합니다. 코드는 출력 JSON, 허용된 finding code와 status, 문서 참조, 인용문이 해당 원문에 실제 포함되는지 확인한 뒤 규칙을 적용합니다. 모델이 불확실하거나 근거가 모순되거나 필수 근거가 부족하면 이를 음성으로 바꾸지 않고 실행 오류로 처리합니다.

### 입력

- `request`: `request_id`, `input_snapshot_id`, `scope`, `dependencies`, `evaluated_at`
- `snapshot`: `snapshot_id`, `known_at`, `facts`
- 문서 Fact는 `document:<document_id>@<version>` 키를 사용하고, `value` 안에 문서 ID·버전·원문을 포함합니다.
- `services.backend`: 합성 실행에서는 고정 backend, 실제 추론에서는 `ScreeningLLMBackend`를 전달합니다.

`scope`의 항목과 `snapshot.facts`의 항목은 일치해야 합니다. 문서 원문은 Snapshot에 범위가 지정되어 전달되며 Screening 모듈이 별도 자료 API를 호출하지 않습니다.
문서는 1~25개까지 처리하며, 각 원문은 40,000자 이하여야 합니다.

### 입력 예시

```json
{
  "request": {
    "request_id": "SCREEN-001",
    "input_snapshot_id": "snapshot-screen-001",
    "scope": ["document:NOTE-01@1"],
    "dependencies": [
      {"system": "SYNTHETIC", "record_id": "NOTE-01", "version": 1, "field": "text"}
    ],
    "evaluated_at": "2026-10-08T15:00:00+09:00"
  },
  "snapshot": {
    "snapshot_id": "snapshot-screen-001",
    "known_at": "2026-10-08T14:59:00+09:00",
    "facts": {
      "document:NOTE-01@1": {
        "value": {
          "document_id": "NOTE-01",
          "version": 1,
          "document_type": "ED_INITIAL_NOTE",
          "saved_time": "2026-10-08T14:50:00+09:00",
          "text": "14:20경 갑자기 증상이 시작됐고 우측 팔다리에 힘이 빠지며 말을 제대로 하지 못했다."
        },
        "status": "AVAILABLE",
        "source_ref": {"system": "SYNTHETIC", "record_id": "NOTE-01", "version": 1, "field": "text"},
        "source_time": "2026-10-08T14:50:00+09:00",
        "known_at": "2026-10-08T14:59:00+09:00"
      }
    }
  }
}
```

### LLM 추출 형식과 최종 결과

LLM은 `findings` 배열을 반환합니다. 각 항목은 다음 네 필드를 사용합니다.

| 필드 | 허용 값 또는 규칙 |
|---|---|
| `code` | `acute_onset`, `focal_weakness`, `language_or_speech_deficit`, `facial_droop`, `vision_deficit`, `gait_or_coordination_deficit`, `fast_positive`, `no_focal_deficit`, `lkw`, `symptom_discovery`, `seizure`, `trauma`, `hypoglycemia` |
| `status` | `present`, `absent`, `uncertain` |
| `source_ref` | 입력 Snapshot에 포함된 문서 참조 |
| `quote` | 해당 문서에 존재하는 정확한 원문 인용 |

LLM의 내부 반환 예시는 다음과 같습니다. 이 `findings`는 Agent의 최종 반환에 그대로 노출되지 않습니다.

```json
{
  "findings": [
    {
      "code": "acute_onset",
      "status": "present",
      "source_ref": "document:NOTE-01@1",
      "quote": "14:20경 갑자기 증상이 시작됐고"
    },
    {
      "code": "focal_weakness",
      "status": "present",
      "source_ref": "document:NOTE-01@1",
      "quote": "우측 팔다리에 힘이 빠지며"
    }
  ]
}
```

코드는 발병 근거, 국소 신경학적 결손, 상충 여부를 확인해 최종 결과를 정리합니다. Agent의 반환 객체는 다음 세 필드입니다.

```json
{
  "screening_result": "POSITIVE",
  "mock_only": false,
  "basis": [
    "acute_onset [document:NOTE-01@1]: 14:20경 갑자기 증상이 시작됐고",
    "focal_weakness [document:NOTE-01@1]: 우측 팔다리에 힘이 빠지며"
  ]
}
```

`screening_result`는 `POSITIVE` 또는 `NEGATIVE`입니다. 결과를 뒷받침할 수 없거나 검토가 필요한 상황은 정상적인 음성 결과로 반환하지 않고 오류로 종료합니다. `NEGATIVE`는 포괄적인 정상 국소 신경학적 진찰 근거가 있고 상충 소견이 없을 때만 반환하며, 뇌졸중을 배제한다는 의미가 아닙니다. `mock_only`는 합성 고정 결과인지 로컬 모델 결과인지를 나타냅니다.

## 3. Clinical Summary Agent

### 목적과 처리

Orchestrator가 지정한 환자·내원 자료와 질문을 받아 한 번의 호출로 질문별 Summary를 생성합니다. 구조화 자료는 코드가 분류하고, 문서 원문은 내부 LLM이 사실과 인용을 추출합니다. 코드는 환자·내원·문서 버전, 질문, 값 타입, 상태, 출처와 인용을 검증하고 여러 자료의 상충을 보존합니다.

### 입력

| 필드 | 의미 |
|---|---|
| `patient_id` | 자료의 환자 일치 검증 |
| `encounter_id` | 문서의 내원 일치 검증 |
| `episode_id` | 반환 결과를 임상 에피소드에 연결 |
| `input_references` | 읽을 문서·구조화 자료의 명시적 범위 |
| `questions` | 추출할 항목 ID 목록. 자유 문장 질문은 받지 않음 |

지원하는 참조는 `document:<문서ID>@<버전>`, `medication:active`, `condition:problem_list`, `encounter_history:6m`입니다. 모든 지정 자료는 필수이며 조회나 환자·내원·버전 검증에 실패하면 부분 성공으로 반환하지 않습니다.
문서 자료의 `document_type`은 `ED_INITIAL_NOTE` 또는 `ED_TRIAGE_NOTE`, `status`는 `CURRENT` 또는 `SUPERSEDED`여야 하며, 요청한 문서 버전과 응답 버전이 일치해야 합니다.

자료 조회 서비스가 반환할 구조화 응답의 최소 형태는 다음과 같습니다.

| 참조 | 응답 필드 | 코드의 처리 방식 |
|---|---|---|
| `document:<id>@<version>` | `document_id`, `version`, `patient_id`, `encounter_id`, `document_type`, `status`, `text` | 환자·내원·문서 버전·유형·상태를 확인한 뒤 원문을 추출기로 전달 |
| `medication:active` | `medications[]`; 각 행에 `status`, `drug_class_flags.anticoagulant`, `drug_class_flags.antiplatelet` | `status: ACTIVE`인 행을 분류. 분류값이 없으면 불확실 정보로 기록 |
| `condition:problem_list` | `conditions[]`; 각 행에 `category`, `status`, `code` | 유효한 문제 목록의 코드로 환자 과거 뇌졸중/TIA를 확인 |
| `encounter_history:6m` | `window_months: 6`, `encounters[]`; 행별 `current`, `surgery`, `bleeding_event`, `procedures` | 최근 6개월의 수술·출혈 정보를 정리. 불명확한 플래그나 미분류 시술은 미확인으로 남김 |

지원 질문 및 `documented` 상태의 값 형식은 다음과 같습니다.

| Question ID | 값 형식 | 의미 |
|---|---|---|
| `anticoagulant_use` | Boolean | 환자 본인의 현재 항응고제 복용 여부 |
| `antiplatelet_use` | Boolean | 환자 본인의 현재 항혈소판제 복용 여부 |
| `recent_surgery` | Boolean | 제공된 최근 병력 범위의 수술 여부 |
| `recent_bleeding` | Boolean | 제공된 최근 병력 범위의 출혈 여부 |
| `recent_surgery_or_bleeding` | 요청 별칭 | `recent_surgery`, `recent_bleeding` 두 결과로 확장 |
| `previous_stroke` | Boolean | 환자 본인의 과거 뇌졸중/TIA. 가족력과 현재 의심 사건은 제외 |
| `lkw_records` | 시간 객체 | 이번 사건의 마지막 정상 확인 시각. 발병·발견·기록 작성 시각과 구분 |

`anticoagulant_use`가 요청되면 `antiplatelet_use`도 함께 처리합니다. 중복 질문은 제거하고 정해진 질문 순서로 반환합니다. Boolean 상태는 약물명과 용량이 아니라 해당 범주의 사용 여부를 나타내며, 구체적 약물 정보는 근거에 보존합니다. 활성 약물 목록이나 문제 목록에 항목이 없다는 사실만으로 `false`를 만들지 않습니다.

### 입력 예시

```json
{
  "patient_id": "PAT-01",
  "encounter_id": "ENC-01",
  "episode_id": "EP-01",
  "input_references": [
    "document:NOTE-01@1",
    "medication:active"
  ],
  "questions": ["anticoagulant_use", "previous_stroke", "lkw_records"]
}
```

### 상태와 반환 결과

각 결과 항목은 `question`, `status`, `value`, `evidence`, `alternatives`를 가집니다.

| `status` | 의미 | `value` |
|---|---|---|
| `documented` | 자료에 답이 명시됨. 명시적 부정도 포함 | 해당 질문의 실제값. Boolean 질문은 `true` 또는 `false` |
| `not_stated` | 검토한 자료에 언급이 없음 | `null` |
| `explicitly_unknown` | 모름·확인 불가·미문진·미평가라고 명시됨 | `null` |
| `conflicting` | 동일 질문에 서로 다른 자료가 상충함 | `null`; 서로 다른 후보는 `alternatives`에 보존 |
| `not_applicable` | 합의된 규칙상 해당 없음 | `null`; 현재 지원 질문에서는 생성하지 않음 |

`evidence`에는 원문 인용 `{source_ref, quote}` 또는 구조화 자료 `{source_ref, record}`가 들어갑니다. 시간 값은 `kind`, `start`, `end`, `precision`, `original_text`를 사용합니다. `missing_information`에는 미기록, 미확인, 상충 및 자료 범위의 한계를 기록합니다.

반환 객체의 상위 필드는 `schema_version`, `episode_id`, `encounter_id`, `input_references`, `questions`, `items`, `missing_information`, `model_info`, `mock_only`입니다. 결과 예시는 다음과 같습니다.

LLM의 내부 반환 구조는 `facts`와 `reviewed_documents`입니다. 코드가 질문·상태·값 타입·문서 출처·인용을 확인하고 구조화 자료와 결합한 뒤 최종 객체를 만듭니다.

```json
{
  "facts": [
    {
      "question": "anticoagulant_use",
      "status": "documented",
      "value": true,
      "evidence": [
        {"source_ref": "document:NOTE-01@1", "quote": "현재 항응고제 apixaban 5 mg bid를 복용 중이다"}
      ]
    }
  ],
  "reviewed_documents": ["document:NOTE-01@1"]
}
```

```json
{
  "schema_version": "summary-items/v1",
  "episode_id": "EP-01",
  "encounter_id": "ENC-01",
  "input_references": ["document:NOTE-01@1"],
  "questions": ["anticoagulant_use"],
  "items": [
    {
      "question": "anticoagulant_use",
      "status": "documented",
      "value": true,
      "evidence": [
        {"source_ref": "document:NOTE-01@1", "quote": "현재 항응고제 apixaban 5 mg bid를 복용 중이다"}
      ],
      "alternatives": []
    }
  ],
  "missing_information": [],
  "model_info": {
    "rule_set": "summary-reconcile/v1",
    "llm_tier": "INTERNAL_ON_PREM",
    "model_key": "qwen35_9b",
    "extraction_method": "direct",
    "confidence_policy": "No uncalibrated confidence score is emitted."
  },
  "mock_only": false
}
```

## 4. tPA Decision Support Agent

### 목적과 처리

전달받은 구조화 임상 정보를 읽기 전용으로 사용하고, 결정론적 프로토타입 규칙 12개를 적용해 평가 항목과 의료진 확인이 필요한 내용을 반환합니다. LLM이나 자료 조회 API를 호출하지 않습니다.

### 입력

- `request`: `request_id`, `mode` (`interim` 또는 `final`), `input_snapshot_id`, `scope`, `dependencies`, `evaluated_at`
- `snapshot`: `snapshot_id`, `known_at`, `facts`
- 각 Fact는 최소한 `value`, `status`, `source_ref`, `source_time`, `known_at`를 포함하고, 수치 값은 필요에 따라 `unit`을 포함합니다.
- `scope`와 Snapshot의 Fact 이름은 일치해야 합니다.

주요 Fact 이름은 `lkw`, `ncct_completed`, `ncct_order_id`, `ct_order_id`, `platelet_count`, `inr`, `anticoagulant`, `weight_kg`, `sbp`, `dbp`, `glucose`, `recent_surgery_or_bleeding`, `previous_stroke`, `nihss`, `antiplatelet`, `age`입니다. 필수 Fact가 없거나 `PENDING`이면 추정하지 않고 미확보 상태로 남깁니다.

### 입력 예시

아래는 시간 정보와 검사 대기 상태만 전달한 `interim` 요청 예시입니다. 미제공 Fact들은 평가 결과에서 범위 밖 또는 미확보 항목으로 표시됩니다.

```json
{
  "request": {
    "request_id": "TPA-001",
    "mode": "interim",
    "input_snapshot_id": "snapshot-tpa-001",
    "scope": ["lkw", "ncct_completed"],
    "dependencies": [
      {"system": "SYNTHETIC", "record_id": "LKW-01", "version": 1, "field": "value"},
      {"system": "SYNTHETIC", "record_id": "CT-01", "version": 1, "field": "value"}
    ],
    "evaluated_at": "2026-10-08T15:00:00+09:00"
  },
  "snapshot": {
    "snapshot_id": "snapshot-tpa-001",
    "known_at": "2026-10-08T14:59:00+09:00",
    "facts": {
      "lkw": {
        "value": "2026-10-08T13:35:00+09:00",
        "status": "AVAILABLE",
        "source_ref": {"system": "SYNTHETIC", "record_id": "LKW-01", "version": 1, "field": "value"},
        "source_time": "2026-10-08T14:50:00+09:00",
        "known_at": "2026-10-08T14:59:00+09:00"
      },
      "ncct_completed": {
        "value": null,
        "status": "PENDING",
        "source_ref": {"system": "SYNTHETIC", "record_id": "CT-01", "version": 1, "field": "value"},
        "source_time": "2026-10-08T14:59:00+09:00",
        "known_at": "2026-10-08T14:59:00+09:00"
      }
    }
  }
}
```

### 반환 결과

최상위 반환 필드는 `mode`, `evidence_package`, `assessment`, `mock_only`입니다. `assessment`에는 다음 정보가 포함됩니다.

| 필드 | 내용 |
|---|---|
| `schema`, `rule_set` | 결과 스키마와 적용 규칙 버전 |
| `status` | `BLOCKING_FINDING_IDENTIFIED`, `INCOMPLETE_PENDING_DATA`, `PHYSICIAN_REVIEW_REQUIRED` 중 하나 |
| `checks` | 12개 평가 항목. 각 항목은 ID, 설명, 결과, 값, 세부 정보, 환자 Fact 근거, 문헌 출처 ID를 포함 |
| `missing_information` | 필수 정보 중 누락·대기·범위 밖인 Fact |
| `scope_gaps` | 요청 범위에서 빠진 평가 항목 |
| `items_requiring_physician_confirmation` | 의료진 확인이 필요한 항목 ID |
| `dose_preview` | 참고용 산술 미리보기. 자동 처방·투약은 수행하지 않음 |
| `limitations` | 프로토타입의 한계 및 유의 사항 |
| `recommendation_type`, `physician_decision_required` | 의사결정지원 전용이며 의료진 판단이 필요함을 표시 |

개별 check 결과는 `PASS`, `FAIL`, `INFO`, `PENDING`, `CONFLICT`, `NOT_IN_SCOPE`, `PASS_UNCONFIRMED`, `PASS_WITH_FLAG`, `REQUIRES_PHYSICIAN_READ`, `REQUIRES_PHYSICIAN_REVIEW` 중 하나입니다. 예를 들어 `ncct_completed=true`는 검사 완료만 나타내며 출혈이 없다는 판독으로 간주하지 않습니다. 정상 범위의 수치도 치료 적합 판정으로 바꾸지 않습니다.

실제 응답의 check 한 건은 아래 구조를 사용합니다. `assessment.checks`에는 같은 형식의 항목 12개가 반환됩니다.

```json
{
  "check_id": "C01_TIME_WINDOW",
  "label": "LKW standard 4.5-hour window",
  "result": "PASS",
  "value": {
    "elapsed_seconds": 5100.0,
    "deadline": "2026-10-08T18:05:00+09:00"
  },
  "detail": "Unknown-onset/extended-window imaging selection requires specialist review.",
  "evidence": [
    {
      "field": "lkw",
      "status": "AVAILABLE",
      "source_ref": {"system": "SYNTHETIC", "record_id": "LKW-01", "version": 1, "field": "value"},
      "source_time": "2026-10-08T14:50:00+09:00",
      "known_at": "2026-10-08T14:59:00+09:00"
    }
  ],
  "source_ids": ["AHA2026"]
}
```

## 5. Orchestrator 및 Tool/API 연동

### 실행 흐름

```text
Orchestrator가 Agent를 선택
        ↓
선택된 Agent에 요청 자료와 실행 서비스를 전달
        ↓
선택된 Agent의 invoke(request, snapshot, services) 호출
        ↓
Agent가 업무 결과를 반환
```

Agent에서 입력 검증, 자료 조회 또는 모델 처리에 실패하면 예외를 호출자에게 전달합니다. 이를 실행 시스템의 오류 응답으로 변환하는 방식은 연동 시 함께 정리해야 합니다.

### Agent별 연결 지점

| Agent | 코드 진입점 | 입력·도구 연결 방식 |
|---|---|---|
| Screening | `chain_agents.screening.agent.invoke` | `snapshot.facts`에서 문서와 구조화 정보를 받음. `services.backend.select(request, snapshot)`으로 합성 backend 또는 로컬 LLM backend 연결 |
| Summary | `chain_agents.summary.agent.invoke` | `services.data_api`로 요청 자료를 조회하고, `services.extractor`로 문서 내용을 처리 |
| tPA | `chain_agents.tpa.agent.invoke` | `snapshot.facts`에 포함된 구조화 정보만 사용. 현재 `services`는 사용하지 않음 |

Summary는 요청한 자료를 검증한 뒤 질문별 결과를 반환합니다. 자료를 확인했으나 답이 없는 경우와 자료 조회·검증에 실패한 경우를 구분합니다.

## 6. 실행 방법

Python 3.11 이상 환경에서 저장소 루트에서 실행합니다.

### 합성 입력으로 세 Agent 확인

```bash
python -m examples.run screening
python -m examples.run summary
python -m examples.run tpa
python -m examples.run all
```

이 예제는 합성 자료를 이용합니다. Screening은 고정 synthetic backend를, Summary는 fixture 추출 결과를 사용하므로 이 명령만으로 실제 LLM 추론이 실행되지는 않습니다. tPA는 합성 Snapshot에 결정론적 규칙을 적용합니다.

### 로컬 LLM 실행

Summary와 Screening은 같은 로컬 LLM 실행 환경을 사용합니다. 먼저 대상 서버에 맞는 CUDA 지원 PyTorch를 준비한 뒤, 저장소 루트에서 공통 의존성을 한 번 설치합니다.

```bash
python -m pip install -r requirements-llm.txt
```

아래 Summary 예제는 로컬 가중치를 사용해 실제 추론을 실행합니다.

```bash
python -m examples.summary --model qwen35_9b --gpu 2 --model-dir /path/to/Qwen3.5-9B
python -m examples.summary --model gemma4_12b_it --gpu 3 --model-dir /path/to/gemma-4-12B-it
```

Screening은 처음 실행하기 전에 고정된 모델 버전을 내려받고 확인합니다. 모델 파일은 별도로 지정한 모델 디렉터리에 보관합니다.

```bash
python scripts/screening_experiment.py download --model qwen35_9b --model-root /path/to/models
python scripts/screening_experiment.py check-model --model qwen35_9b --model-root /path/to/models
python scripts/screening_model_demo.py --model qwen35_9b --gpu 2 --model-root /path/to/models
```

모델을 내려받은 뒤에는 추론 과정에서 외부 모델 서비스에 연결하지 않습니다.

tPA의 합성 시나리오는 다음과 같이 실행합니다.

```bash
python -m chain_agents.tpa.demo interim
python -m chain_agents.tpa.demo final
python -m chain_agents.tpa.demo high-bp
python -m chain_agents.tpa.demo low-platelets
```

### 자동 테스트

```bash
python -m unittest discover -s tests -v
```

## 7. 향후 보완 사항

| 과제 | 현재 상태 | 다음 작업 |
|---|---|---|
| Orchestrator 연동 | Agent별 입력과 결과를 Orchestrator와 함께 통합 검증하는 작업이 남아 있습니다. | 실제 호출 흐름에 맞춰 입력 연결과 결과 전달을 확인합니다. |
| Agent 실행 오류 | 입력·자료 조회·모델 처리 실패는 예외로 전달합니다. 이를 실행 시스템의 오류 응답으로 변환하는 방식은 함께 정리해야 합니다. | 실행 실패와 정상적인 임상 검토 결과가 구분되도록 연결 방식을 확인합니다. |
| Summary 갱신 | 현재 요청 자료를 바탕으로 Summary를 새로 생성해 반환합니다. 기존 Summary에 새 자료를 반영하는 갱신 기능은 구현되어 있지 않습니다. | 필요한 갱신 동작을 정하고 구현합니다. |

## 8. 코드 구성

| 경로 | 역할 |
|---|---|
| `chain_agents/screening/agent.py`, `prototype.py`, `local_model.py` | Screening 진입점, 근거 검증·선별 로직, 로컬 모델 연결 |
| `chain_agents/summary/agent.py`, `summary.py`, `data_contract.py`, `contract.py`, `extractor.py` | Summary 진입점, 자료 조회·질문별 결합·반환 검증·LLM 추출 |
| `chain_agents/tpa/agent.py`, `logic.py`, `rules.py`, `policy.py` | tPA 진입점, 규칙 평가와 프로토타입 정책 |
| `chain_agents/services.py` | Agent에 전달하는 backend, 자료 조회, 추출, 입력 감사 서비스 컨테이너 |
| `examples/` | 합성 입력, 실행 예제, fixture 기반 서비스 |
| `tests/` | 호출 계약, 입력 검증, 도메인 규칙 확인 |
