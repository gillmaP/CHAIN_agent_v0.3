# Orchestrator 연결과 통합 예제

## 현재 v0.3 plugin 경로

| Alias | Entrypoint | 현재 모드 | 서비스 |
|---|---|---|---|
| `stroke_screening` | `chain_agents.screening.agent:invoke` | `screening` | mock/local backend |
| `clinical_summary` | `chain_agents.summary.agent:invoke` | `context` | cache |
| `tpa_decision_support` | `chain_agents.tpa.agent:invoke` | `interim`, `final` | 공통 service object |

Orchestrator Runtime은 v0.3 request/snapshot을 검증하고 `invoke(request, snapshot, services)`를 호출한 뒤 도메인 결과를 공통 envelope로 감쌉니다. Screening `invoke_v012`는 별도 Mock v0.12 adapter입니다.

## AgentServices extension point

이 repo의 `chain_agents.services.AgentServices`는 worker-local `cache`, `backend`, `data_api`, `extractor`, `input_observer`를 전달합니다. 그러나 확인한 upstream Runtime은 `cache`와 선택적인 fixture `backend`만 생성합니다. Summary S1을 실제 upstream worker에서 실행하려면 Runtime service factory에 권한 기반 data API와 모델 추출기를 추가하고, S1 입력/output의 등록 계약도 갱신해야 합니다. 그 전까지 S1은 `examples.run_integrated`의 합성 module call로 시연합니다.

## 실행

```bash
python -m examples.run all
python -m examples.run_integrated
```

두번째 예제는 세 Agent의 호출 모양을 한 파일에서 보여줍니다. 각 Agent에 별도 입력을 사용하며, Agent 출력 사이를 자동 변환하지 않습니다. 하나의 clinical pipeline이나 실제 모델 결과를 나타내지 않습니다.

## Upstream 사본 생성

```bash
python scripts/prepare_integration.py --upstream ../chain-orchestrator-v03 \
  --output ../chain-integration-demo --synthetic-demo
```

기존 scaffold는 v0.3 plugin modes를 별도 Orchestrator 사본에 등록합니다. Summary `s1` mode와 추가 services를 등록하지 않습니다.

## 실제 연동에 필요한 단계

1. 하이젠 REST API의 경로, 인증, 버전과 시점 의미를 확정합니다.
2. Runtime worker에 권한이 제한된 `data_api`를 생성해 필요한 Agent에 주입합니다.
3. Summary extractor와 Screening 모델 backend를 worker-local factory에서 생성·재사용합니다.
4. Summary S1 요청을 workflow scope/snapshot으로 바꾸는 입력 adapter를 합의합니다.
5. Agent별 result key를 workflow output, 저장 경로, UI query와 연결합니다.
6. request ID, retry/timeout, audit, 저장 보존기간, notifier 담당을 정합니다.
7. Registry file hashes를 다시 만들고 Local Engine 및 Temporal 경로를 검증합니다.

실제 EMR/OCS, credentials, UI, notifier를 이 repo가 운영하지 않습니다.
