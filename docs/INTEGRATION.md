# Orchestrator 연결

## 공통 호출

각 Agent는 다음 형태로 호출됩니다.

    invoke(request, snapshot, services) -> dict

Agent는 요청된 작업을 처리해 도메인 결과를 반환합니다. Orchestrator Runtime은 실행 envelope와 workflow 상태를 관리합니다.

## Summary 호출 경로

| 경로 | 입력 | 결과 | 역할 |
|---|---|---|---|
| S1 | episode/encounter, 자료 참조, 질문 | 질문별 items, missing information | 이 프로젝트에서 구현하는 Summary 흐름 |
| context | v0.3 scoped snapshot facts | structured_context, missing_information, cache | 기존 starter 계약과의 호환 경로 |

context는 원래 v0.3 starter에 있던 snapshot 요약 경로입니다. S1과는 입력·결과가 다르며, S1 workflow의 두 번째 요약 단계가 아닙니다.

## Summary 서비스

| 서비스 | 호출 형태 | 용도 |
|---|---|---|
| data_api | get(path) -> dict | 참조된 구조화 자료와 문서 조회 |
| extractor | extract(documents, questions) -> dict | 문서 원문에서 질문별 사실과 인용 추출 |
| input_observer | callback | 선택적인 입력 감사 정보 저장 |

Host의 service factory가 필요한 구현을 만들어 AgentServices에 전달합니다. Summary의 endpoint 요청 형식과 자료 검증 규칙은 chain_agents/summary/data_contract.py 및 chain_agents/summary/site_data_api.py에 있습니다.

## 참조 Orchestrator에 연결

현재 참조 설정은 clinical_summary를 기존 context 경로로 호출합니다. S1을 연결할 때는 workflow의 S1 요청을 Summary 형식으로 전달하고, Runtime service factory에서 data_api와 extractor를 주입합니다. 반환된 items는 Runtime의 결과 저장·조회 경로에 연결합니다.

Screening과 tPA도 같은 Python 진입점을 사용합니다. Screening은 backend를, tPA는 요청 snapshot을 사용합니다. Agent별 입력과 결과를 Orchestrator의 workflow 계약에 맞춰 등록합니다.

## 합성 실행

저장소 루트에서 실행합니다.

    python -m examples.run all
    python -m examples.run_integrated

run_integrated는 각 Agent를 합성 입력으로 호출해 연결 형태를 보여줍니다. Summary S1은 고정 합성 extractor를 사용합니다.

## 설정 사본 생성

    python scripts/prepare_integration.py --upstream ../chain-orchestrator-v03 --output ../chain-integration-demo --synthetic-demo

이 스크립트는 참조 Orchestrator의 별도 사본에 현재 v0.3 plugin 구성을 생성합니다. Summary S1을 사용하는 구성은 S1 요청과 서비스를 연결한 뒤 등록합니다.
