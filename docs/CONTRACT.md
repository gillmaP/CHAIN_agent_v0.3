# Agent 요청과 반환 결과

세 Agent는 같은 Python 함수 형태로 불립니다.

```python
invoke(request, snapshot, services) -> dict
```

공통점은 호출 경계와 오류 처리입니다. 의료 업무가 다르므로 모든 Agent에 같은 임상 필드나 결과 형식을 강제하지 않습니다. Orchestrator가 등록 정보나 API 경로로 Agent를 선택하므로 요청 본문에 `agent`·`action`을 반복하지 않습니다.

## Summary

### 요청

```json
{
  "patient_id": "PAT-example",
  "encounter_id": "ENC-example",
  "episode_id": "EP-example",
  "input_references": ["document:NOTE-example@1"],
  "questions": ["anticoagulant_use"]
}
```

`input_references`는 조회 가능한 환자 자료를 지정하고 `questions`는 답을 요청하는 항목을 지정합니다. Summary는 한 번 호출해 모든 요청 질문의 결과를 돌려줍니다.

### 반환

```json
{
  "schema_version": "summary-items/v1",
  "episode_id": "EP-example",
  "encounter_id": "ENC-example",
  "input_references": ["document:NOTE-example@1"],
  "questions": ["anticoagulant_use", "antiplatelet_use"],
  "items": [
    {
      "question": "anticoagulant_use",
      "status": "documented",
      "value": true,
      "evidence": [
        {"source_ref": "document:NOTE-example@1", "quote": "현재 항응고제를 복용 중이다"}
      ],
      "alternatives": []
    },
    {
      "question": "antiplatelet_use",
      "status": "documented",
      "value": true,
      "evidence": [
        {"source_ref": "document:NOTE-example@1", "quote": "항혈소판제를 복용 중이다"}
      ],
      "alternatives": []
    }
  ],
  "missing_information": []
}
```

질문 ID별 값 타입과 `status`, `evidence`, `alternatives` 규칙은 [Summary 계약](../chain_agents/summary/CONTRACT.md)에 정의되어 있습니다.

## Screening

Screening은 승인된 기록과 구조화된 정보를 받아 기록 근거를 검토하고 선별 결과를 반환합니다. 기본 Python 호출은 `chain_agents.screening.agent.invoke`이며, 필요한 스코프 자료와 실행 backend는 Host가 전달합니다. 상세 샘플과 모델 실행 방법은 [Screening 안내](../chain_agents/screening/README.md)를 참고하세요.

## tPA Decision Support

tPA는 Orchestrator가 선택한 평가 단계와 구조화 facts를 입력받습니다. `interim`과 `final`은 별도의 임상 시점이며, 각 요청은 같은 `chain_agents.tpa.agent.invoke` 진입점을 사용합니다. 결과는 평가 항목과 판단에 사용한 입력 근거를 담습니다. 상세 값은 [tPA 안내](../chain_agents/tpa/README.md)에 있습니다.

## 오류와 상태

- Agent는 실행 실패를 임상 `false`나 빈 정상 결과로 바꾸지 않고 예외를 냅니다.
- Summary의 `not_stated`는 성공적으로 확인한 자료에 언급이 없다는 뜻입니다. 자료 API 오류는 실행 실패입니다.
- Agent는 도메인 결과만 반환합니다. Host/Orchestrator가 실행 상태와 결과 envelope를 관리합니다.
- 반환 결과는 입력 자료의 출처를 보존합니다. 입력 객체를 변경하지 않습니다.
