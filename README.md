# CHAIN Agent Modules

Stroke Screening, Clinical Summary, tPA Decision Support를 하나의 Python 저장소에서 개발합니다. 각 모듈은 공통 Python 진입점으로 호출되고, 요청한 작업에 맞는 결과를 반환합니다.

## 빠른 실행

Python 3.11 이상, 저장소 루트에서 실행합니다.

    python -m examples.run all
    python -m examples.run_integrated
    python -m unittest discover -s tests -v

두 예제는 합성 자료로 동작합니다. 첫 번째는 기본 v0.3 호출 경로를 실행하고, 두 번째는 Summary S1 경로까지 포함해 세 모듈을 호출합니다.

## Agent 역할

| Agent | 주요 입력 | 결과 |
|---|---|---|
| Stroke Screening | 요청과 scoped snapshot | screening 결과와 근거 |
| Clinical Summary S1 | episode, 자료 참조, 추출 질문 | 질문별 items와 missing information |
| tPA Decision Support | 요청과 scoped snapshot | interim/final assessment |

세 모듈의 공개 호출 형태는 다음과 같습니다.

    invoke(request, snapshot, services) -> dict

Orchestrator Runtime은 반환된 도메인 결과를 공통 실행 결과에 담습니다. 호출 시점과 workflow 상태, 재시도, HITL은 Orchestrator가 관리합니다.

## Summary S1은 무엇을 하나요?

Summary의 주요 작업은 workflow가 S1에 들어갈 때 요청받은 질문에 답할 수 있도록 지정된 자료를 모으고 정리하는 것입니다.

1. Orchestrator가 episode, encounter, 자료 참조, 질문 목록을 전달합니다.
2. Summary가 서비스 인터페이스를 통해 약물·문제 목록·최근 내원·문서 자료를 가져옵니다.
3. 코드가 구조화 자료를 처리하고, 내부 LLM이 문서 원문에서 질문에 필요한 사실과 인용을 추출합니다.
4. 코드가 출력 형식과 출처를 검증한 뒤 질문별 items와 missing information을 반환합니다.

코드에는 v0.3 starter에서 이어진 context 호환 모드도 남아 있습니다. 이 모드는 이미 snapshot에 담긴 구조화 facts를 받아 structured_context를 반환합니다. S1과 context는 서로 다른 요청 경로이며, 하나의 Summary workflow 안에서 차례로 실행되는 두 단계가 아닙니다. 현재 프로젝트의 Summary 기능은 S1 흐름을 기준으로 설명합니다.

## Orchestrator 연결

서비스는 Host가 만들고 Agent에 전달합니다.

| 서비스 | 사용 모듈 | 인터페이스 |
|---|---|---|
| backend | Screening | 합성 또는 실행 환경의 screening backend |
| data_api | Summary S1 | get(path) -> dict |
| extractor | Summary S1 | extract(documents, questions) -> dict |
| cache | context compatibility | snapshot 결과 cache |
| input_observer | Summary S1 | 선택적인 입력 감사 callback |

참조 Orchestrator 설정의 Summary 항목은 기존 context 모드로 구성되어 있습니다. S1을 실행하려면 S1 요청의 자료 참조·질문을 전달하고, Host의 service factory가 data_api와 extractor를 주입하도록 연결합니다. Summary의 자료 조회 경로는 chain_agents/summary/data_contract.py에, 호출 예제는 chain_agents/summary/README.md에 있습니다.

## 코드와 상세 문서

- 공통 계약: [docs/CONTRACT.md](docs/CONTRACT.md)
- Orchestrator 연결: [docs/INTEGRATION.md](docs/INTEGRATION.md)
- Screening: [chain_agents/screening/README.md](chain_agents/screening/README.md)
- Summary: [chain_agents/summary/README.md](chain_agents/summary/README.md)
- tPA: [chain_agents/tpa/README.md](chain_agents/tpa/README.md)
- 예제 실행: [examples/run.py](examples/run.py), [examples/run_integrated.py](examples/run_integrated.py)
