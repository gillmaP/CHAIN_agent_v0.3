# Orchestrator 연동 안내

## 기본 흐름

```text
Orchestrator가 업무 단계에서 Agent를 선택
             ↓
Host가 해당 Agent의 request / snapshot / services 준비
             ↓
invoke(request, snapshot, services)
             ↓
Agent가 업무 결과를 반환
             ↓
Host가 실행 결과를 저장하고 필요한 화면에 제공
```

세 모듈은 같은 Python 진입점 형태를 사용합니다. 입력과 출력 필드는 업무에 맞게 각자 정의합니다.

| Agent | 필요한 입력 | 실행 서비스 | 주요 결과 |
|---|---|---|---|
| Screening | 문서와 구조화된 선별 정보 | Screening backend / 내부 모델 | 선별 결과와 근거 |
| Summary | 환자·내원 ID, 자료 참조, 질문 | 승인된 자료 조회기와 내부 문서 추출기 | 질문별 `items`와 `missing_information` |
| tPA | 평가 단계와 구조화 facts | 없음 | `assessment`와 `evidence_package` |

## Agent 선택과 업무 요청

실행 시스템에는 Agent를 고를 선택자가 필요합니다. 이 선택은 Orchestrator 등록 정보나 API 경로에 둡니다. Orchestrator가 job envelope에 등록 alias를 넣는 방식도 가능합니다. 이는 세 업무를 하나로 묶는 것이 아니라 각 호출의 수신 모듈을 정하는 일입니다.

임상 입력 본문에는 `agent`를 중복해서 넣지 않습니다. 하나의 작업만 하는 Summary에는 `action: build_summary`도 두지 않습니다. Summary는 요청의 `questions` 전체를 한 번에 처리합니다. 반면 tPA의 `mode`는 interim/final 평가 단계를 구분하므로 요청에 남습니다.

## Summary 요청

```json
{
  "patient_id": "PAT-example",
  "encounter_id": "ENC-example",
  "episode_id": "EP-example",
  "input_references": ["document:NOTE-example@1", "medication:active"],
  "questions": ["anticoagulant_use", "previous_stroke", "lkw_records"]
}
```

요청에 필요한 의미는 다음 다섯 가지입니다.

| 필드 | 이유 |
|---|---|
| `patient_id` | 자료가 해당 환자에 속하는지 확인 |
| `encounter_id` | 문서가 해당 내원에 속하는지 확인 |
| `episode_id` | 반환 Summary를 관련 임상 에피소드에 연결 |
| `input_references` | 읽을 문서와 구조화 자료 범위 지정 |
| `questions` | 필요한 임상 항목만 요청 |

별도 `action` 값은 없습니다. 모델은 원문 자료와 질문 정의를 받아 사실·인용을 추출하고, 코드는 상태·값·인용·출처와 입력 범위를 확인합니다. 세부 계약은 [Summary 입출력](../chain_agents/summary/CONTRACT.md)을 참고하세요.

## 자료 조회와 모델 실행

Summary Agent는 `services.data_api.get(path)`와 `services.extractor.extract(documents, questions)` 인터페이스를 사용합니다. Host는 인증과 접근 제어를 거친 자료 조회기를 연결하고, 내부 모델 추론기를 제공합니다. Agent 저장소에는 병원별 EMR/OCS API 구현이나 HTTP 서버가 없습니다.

조회할 자료가 하나라도 누락되거나 환자·내원·버전 검증에 실패하면 Summary는 정상 결과를 반환하지 않고 오류를 냅니다. 자료를 성공적으로 읽고 해당 질문의 정보가 없을 때에만 `not_stated`를 반환합니다.

## 결과 저장과 화면 표시

Summary 호출은 질문별 items와 미확인 정보를 포함한 결과를 한 번 반환합니다. Host는 이 결과를 저장하고 환자 화면이나 후속 요청에서 읽을 수 있게 합니다. 화면에서 저장 결과를 보여줄 때 Summary 모델을 다시 호출할 필요는 없습니다.

`invoke`가 반환하는 것은 Agent 업무 결과뿐입니다. 실행 ID, 실행 성공·실패, 재시도, 결과 저장 위치, 화면 알림은 Host/Orchestrator가 관리합니다.

## Orchestrator 코드와 맞출 최소 항목

현재 공유된 Orchestrator 구현을 그대로 계약으로 고정할 필요는 없습니다. Summary 통합을 위해 필요한 변경은 다음 정도입니다.

1. Summary 등록 정보를 한 번의 질문 처리 함수에 연결하고, 워크플로 상태별 Summary 변형을 만들지 않습니다.
2. 요청 검증기가 위 Summary 전용 입력 필드를 허용합니다. 각 Agent가 다른 업무 입력을 갖는 것은 정상입니다.
3. Host가 자료 조회기와 내부 추출기를 Agent 실행 환경에 제공합니다. Orchestrator가 직접 EMR/OCS 구현을 맡을 필요는 없습니다.
4. 반환된 Summary를 저장하고 UI가 저장 결과를 읽을 수 있게 합니다.

이 네 항목은 각각 라우팅, 입력, 필요한 실행 자원, 결과 재사용을 위한 최소 조건입니다. `agent`와 `action`을 임상 본문에 추가하거나 두 번 호출하는 방식은 이 작업에 필요하지 않습니다. 단, Orchestrator가 단일 고정 작업도 mode 등록을 요구한다면 Summary 실행기는 내부 기본값으로 처리하고 임상 요청에 별도 action을 요구하지 않는 쪽이 단순합니다.

## 다른 Agent

Screening 및 tPA도 각각 독립 진입점을 사용합니다. Screening은 원문 근거를 선별 규칙에 연결하고, tPA는 전달받은 구조화 facts를 규칙으로 확인합니다. 다른 Agent의 업무 결과를 Summary 요청에 합치거나 Agent끼리 직접 호출하지 않습니다.

실행 예시는 저장소 루트에서 `python -m examples.run all`, 테스트는 `python -m unittest discover -s tests -v`입니다.
