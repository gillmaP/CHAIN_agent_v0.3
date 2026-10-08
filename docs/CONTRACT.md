# Agent별 입력과 결과

이 문서는 각 Agent에 전달하는 입력과 Agent가 돌려주는 결과를 설명합니다.

## 기본 호출 모양

```python
invoke(request, snapshot, services) -> dict
```

- `request`: 실행할 작업과 필요한 입력
- `snapshot`: 호출 시점에 전달되는 구조화 자료. 호출 방식에 따라 사용하지 않을 수 있습니다.
- `services`: 자료 조회나 모델 실행처럼 Agent가 사용할 기능
- 반환값: Agent별 업무 결과를 담은 Python 사전

Orchestrator 실행 환경은 이 결과를 받아 저장하거나 다음 업무 단계에 전달합니다.

## Agent별 요약

| Agent와 호출 방식 | 입력 | 결과 |
|---|---|---|
| Screening / `screening` | 요청과 구조화 자료 | 선별 결과와 근거 |
| Summary / `context` | 이미 정리된 구조화 자료 | `structured_context`, 누락 정보, cache |
| Summary / `s1` | 환자·내원 정보, 자료 목록, 질문 | 질문별 답·근거인 `items`, `missing_information` |
| tPA / `interim`, `final` | 요청과 구조화 자료 | 검토 항목과 assessment |

## Summary S1 입력

S1 요청에는 환자·내원 식별 정보, S1 단계가 시작되었다는 표시, 읽을 자료 목록, 답을 원하는 질문이 들어갑니다.

```json
{
  "mode": "s1",
  "patient_id": "PAT-example",
  "encounter_id": "ENC-example",
  "episode_id": "EP-example",
  "trigger": {"state_enter": "S1"},
  "input_references": ["document:NOTE-example@1"],
  "questions": ["anticoagulant_use"]
}
```

이 경로는 별도 snapshot 대신 요청의 자료 참조를 사용합니다. 자료 조회와 문서 추출 기능을 `services`로 전달합니다.

## Summary S1 결과

질문마다 결과를 하나 반환합니다.

```json
{
  "question": "anticoagulant_use",
  "status": "documented",
  "value": true,
  "evidence": [
    {
      "source_ref": "document:NOTE-example@1",
      "quote": "현재 항응고제 apixaban 5 mg bid를 복용 중이다"
    }
  ],
  "alternatives": []
}
```

질문 유형에 따라 `value`의 자료형은 다를 수 있습니다. 예를 들어 사용 여부는 참·거짓, 시간 정보는 시간 필드가 있는 객체입니다. 정보가 없거나 서로 다른 정보가 있는 경우는 `status`로 구분합니다. 자세한 규칙은 [Summary 출력 형식](../chain_agents/summary/CONTRACT.md)을 참고하세요.

## 기존 Summary context 입력

`context`는 처음 Orchestrator 예제에 있던 방식입니다. 요청에 범위가 있고, 그 범위의 구조화 자료가 `snapshot.facts`에 들어 있습니다. Summary는 받은 자료를 정리해 `structured_context`를 반환합니다.

S1은 자료를 직접 조회해 질문별 결과를 만듭니다. 둘은 별개의 호출 방식이며 한 흐름의 두 단계가 아닙니다.
