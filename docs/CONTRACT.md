# Agent 호출 및 입출력 계약

## 공통 Python boundary

```python
def invoke(request, snapshot, services) -> dict:
    ...
```

- `request`: mode와 agent별 작업·대상·범위.
- `snapshot`: 승인된 scoped context. v0.3 mode에서는 필수, 현재 Summary `s1` module call에서는 `None`.
- `services`: `chain_agents.services.AgentServices` — `cache`, `backend`, `data_api`, `extractor`, `input_observer`.
- 반환: 도메인 결과 dict. v0.3 공통 envelope는 Orchestrator Runtime이 만듭니다.
- 잘못된 입력·출처·추출은 예외로 실패합니다. 임상 부정 결과로 바꾸지 않습니다.

이 services 객체는 프로세스 안에서 capability를 전달하는 작은 Python 컨테이너입니다. 자체 HTTP server·database·credential lookup이 아닙니다. Host가 실제 clients/model을 준비해 필요한 항목만 주입합니다.

## Orchestrator v0.3 contract

표준 request는 `contract_schema`, `request_id`, `agent_id`, `agent_version`, `manifest_hash`, `mode`, `input_snapshot_id`, `scope`, `dependencies`, `evaluated_at`을 받습니다. Snapshot은 `contract_schema`, `snapshot_id`, `known_at`, `facts`입니다. `facts` key 집합은 `request.scope`와 같아야 합니다.

Runtime은 Agent의 domain dict를 `chain-agent-result/v0.3` envelope의 `result`에 담아 `SUCCESS/FAILED`를 관리합니다.

| Agent / v0.3 mode | Domain result keys |
|---|---|
| Screening / `screening` | `screening_result`, `mock_only`, `basis` |
| Summary / `context` | `structured_context`, `missing_information`, `cache` |
| tPA / `interim`, `final` | `mode`, `evidence_package`, `assessment`, `mock_only` |

## Summary reference-based S1

모듈 예제는 환자·내원·episode ID, `trigger.state_enter=S1`, `input_references`, 고정 `questions`를 받고 `mode=s1`로 호출합니다. 반환은 `summary-s1-fields/v1`의 `items`입니다. 항목마다 `question`, `status`, `value`, `evidence`, `alternatives`를 포함합니다.

이것은 v0.3 request/snapshot 계약과 별도입니다. 현재 upstream request validator는 추가 request fields를 거부하고 Runtime은 snapshot을 항상 넘깁니다. upstream `AgentServices`는 `cache`와 선택적인 fixture `backend`만 제공합니다. S1을 upstream에서 실행하려면 adapter가 v0.3 scope/snapshot을 자료 요청으로 변환하고 승인된 worker service factory에서 `data_api`와 `extractor`를 주입해야 합니다. 이 연결 전에는 local module path입니다.

## 책임 구분

| 기능 | Agent | Host/Orchestrator |
|---|---|---|
| 호출·workflow 전이·HITL | domain result만 생성 | 호출 시점, 상태 전이, HITL |
| 입력 | scope와 출처를 읽고 결과 검증 | scope, snapshot, 접근 권한 제공 |
| 데이터 조회 | 주입 client로 요청 | client·인증·권한 생성 |
| 실행 envelope·ID·retry | 미소유 | Runtime이 관리 |
| 저장·UI·알림 | 미소유 | 정한 Runtime/backend 위치에서 연결 |
