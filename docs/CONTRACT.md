# v0.3 연결 계약

참조: [upstream README §6](https://github.com/donggunseo/chain-orchestrator-v03/tree/00e5bf6c96b61a1a104af249b86a08d682106332), `chain_demo/contracts.py`, `chain_demo/agents/runtime.py`, `config/workflow_v03.yaml`.

## 입력

`request`에는 `contract_schema`, `request_id`, `agent_id`, `agent_version`, `manifest_hash`, `mode`, `input_snapshot_id`, `scope`, `dependencies`, `evaluated_at`이 있습니다. 환자 ID가 별도 최상위 필드로 주어지지 않습니다.

`snapshot`에는 `contract_schema=chain-context/v0.3`, `snapshot_id`, `known_at`, `facts`가 있습니다. `facts` key 집합은 request.scope와 같습니다.

```json
{
  "value": 68,
  "status": "AVAILABLE",
  "source_ref": {
    "system": "CHAIN_INITIAL",
    "record_id": "TEST-EPISODE",
    "version": 1,
    "field": "age"
  },
  "source_time": "2026-10-06T09:00:00+09:00",
  "known_at": "2026-10-06T09:00:00+09:00"
}
```

선택 Fact 필드: `unit`, `confirmation_status`, `dependencies`. false는 명시적 값이고 null은 미확보입니다. NO_EVIDENCE가 임상적으로 확정 음성인 것은 아닙니다. 현재 tPA baseline의 STRUCTURED_MOCK_ONLY는 자료 포장 상태일 뿐 적합성 판정이 아닙니다.

기본 scope:

- Screening: `document:DOC-2610060412`, `lkw`, `glucose`
- Summary: 호출자가 요청한 scope. 기본 예시는 age; 엔진의 ensure_context에서도 사용됨.
- tPA: `lkw`, `ncct_completed`, `ncct_order_id`, `ct_order_id`, `platelet_count`, `inr`, `anticoagulant`, `weight_kg`, `nihss`, `sbp`, `dbp`, `glucose`, `age`

Screening의 문서 ID는 데모용입니다. 실제 환자의 문서 선택 규약은 upstream 팀과 정해야 합니다. tPA scope에 없는 수술/출혈/약물 마지막 복용시각 등을 임의 조회하거나 추정하지 않습니다.

## 책임 분리

| 계층 | 책임 |
|---|---|
| Orchestrator | 호출 시점, scope, 상태전이, HITL, result 수락 |
| AgentRuntime | 입력/등록/파일 hash 검증, 함수 호출, SUCCESS/FAILED envelope |
| 각 팀 Agent | 주어진 입력의 의미를 해석하고 도메인 결과 검증·반환 |
| services | Worker cache와 선택적 fixture backend |

`services.api_client` 또는 `services.llm`은 현재 upstream에 없습니다. 모델 client를 쓰려면 팀 모듈에서 구성하거나 주입 계약을 추가해야 합니다. 비동기 함수로 바로 바꾸면 현재 Runtime 호출 방식과 맞지 않습니다. 외부 SDK 호출은 동기 `invoke` 내부/Activity 경계에 둡니다.

## 현재 버전에서 특별히 합의할 항목

1. Summary의 NLP 결과 저장 경로: 현재 context passthrough equality 제약을 유지할지 별도 도메인 출력으로 확장할지.
2. 실제 모델용 출력 key와 mock_only 제거, enum 및 Workflow 분기.
3. 에피소드별 문서 scope와 추가 의료 Fact 이름.
4. 모델 실패·timeout·미결정 결과 처리와 버전 고정.

v0.12와 v0.3의 차이: v0.3에서는 Summary를 여러 scope로 요청할 수 있고 S2에서 새 근거마다 interim이 호출됩니다. “DSA 두 번 고정”이라는 이전 v0.12 설명을 이 저장소에 적용하지 않습니다. S2_1 진입은 여전히 NCCT 완료와 order 일치 조건입니다.
