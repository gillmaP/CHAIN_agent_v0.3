# CHAIN Agent Modules

Stroke Screening, Clinical Summary, tPA Decision Support를 같은 Python 저장소에서 개발하고 합성 입력으로 호출하는 통합 개발 브랜치입니다. 세 Agent는 같은 Python 진입점 형태를 사용합니다. Agent별 도메인 입력과 결과는 다르며, 공통 호출 규칙과 Orchestrator 연결 경계는 아래 문서에 정리했습니다.

## 빠른 시작

Python 3.11 이상, 저장소 루트에서 실행합니다.

```bash
# v0.3 기본 plugin 합성 예제: Screening, Summary context, tPA interim/final
python -m examples.run all

# 세 Agent 모듈 전체 호출 예제: 위 모드에 reference-based Summary S1 추가
python -m examples.run_integrated
```

예제는 가상 자료와 고정 응답을 사용합니다. 병원 시스템 연결, Temporal 실행, 임상 성능 평가를 뜻하지 않습니다. 실제 Screening·Summary 모델 실행은 Agent README를 참고하세요.

## 작업별 코드와 연결 위치

| 작업 | 코드 | 연결 지점 |
|---|---|---|
| 공통 서비스 주입 | `chain_agents/services.py` | `cache`, `backend`, `data_api`, `extractor`, `input_observer` |
| 공통 v0.3 호출·결과 envelope | `chain_agents/common.py`, Orchestrator AgentRuntime | `invoke(request, snapshot, services) -> dict` |
| Screening | `chain_agents/screening/` | `screening.agent:invoke`; 별도 v0.12 adapter `invoke_v012` |
| Summary context | `chain_agents/summary/` | `summary.agent:invoke`, mode `context` |
| Summary S1 | `chain_agents/summary/` | `summary.agent:invoke`, mode `s1` |
| tPA | `chain_agents/tpa/` | `tpa.agent:invoke`, mode `interim` 또는 `final` |
| 합성 실행 | `examples/run.py`, `examples/run_integrated.py` | GPU·병원 시스템 없이 실행 |
| v0.3 별도 통합 사본 | `scripts/prepare_integration.py` | Catalog/Registry/Policy scaffold |
| 계약·연동 | `docs/CONTRACT.md`, `docs/INTEGRATION.md` | 요청·응답·서비스·Runtime 제약 |

## 공통 호출 계약

```python
def invoke(request, snapshot, services) -> dict:
    """Validate the Agent request and return a domain result."""
```

Orchestrator v0.3은 Agent 반환 dict를 공통 `chain-agent-result/v0.3` envelope에 감싸고 실행 ID, 성공/실패 상태와 evidence를 관리합니다. Agent는 도메인 결과만 반환하며 workflow 전이, HITL, 재시도, 결과 저장, 알림을 직접 처리하지 않습니다.

| Agent / mode | 입력 | Agent 결과의 주요 key |
|---|---|---|
| Screening / `screening` | v0.3 scoped snapshot과 backend | `screening_result`, `mock_only`, `basis` |
| Summary / `context` | v0.3 scoped snapshot facts | `structured_context`, `missing_information`, `cache` |
| Summary / `s1` | episode 식별자, `input_references`, 질문. 현재 모듈 호출에선 `snapshot=None` | `summary-s1-fields/v1`의 질문별 items |
| tPA / `interim`, `final` | v0.3 scoped snapshot과 `evaluated_at` | `mode`, `evidence_package`, `assessment`, `mock_only` |

Summary S1은 현재 공유 Orchestrator v0.3 Runtime에 바로 등록되는 경로가 아닙니다. upstream request validator는 추가 S1 필드를 거부하며 Runtime은 snapshot을 항상 넘기고 `data_api`·`extractor`를 주입하지 않습니다. 실제 S1 연결에는 요청/snapshot adapter, 권한이 있는 service factory, 출력 등록이 필요합니다. `run_integrated`는 로컬 모듈 호출 예제이며 upstream Runtime 통합 완료를 의미하지 않습니다.

## Tool·모델·저장 책임

- Screening과 Summary는 외부 데이터 API 서버를 구현하지 않습니다. Host가 `data_api.get(path)` 클라이언트를 주입할 수 있습니다. 현재 경로는 Mock 계약이며 하이젠 API에 맞춘 연결은 별도입니다.
- tPA는 전달된 snapshot facts에 규칙을 적용합니다.
- Summary S1은 문서용 `extractor`가 필요합니다. 모델·GPU lifecycle과 권한은 Host에서 구성합니다.
- 독립 Summary HTTP server, queue, SQLite result service는 제공하지 않습니다. 결과 저장과 UI 조회는 통합 Runtime/backend에 연결해야 합니다.
- 병원 원문·credentials·모델 가중치·실행 산출물은 Git에 넣지 않습니다. 102 서버의 산출물은 `/data/data2` 또는 `/data/data3`에 저장합니다.

## 세부 문서

- [Orchestrator 통합 안내](docs/INTEGRATION.md)
- [공통·도메인 계약](docs/CONTRACT.md)
- [Screening](chain_agents/screening/README.md)
- [Summary](chain_agents/summary/README.md)
- [tPA](chain_agents/tpa/README.md)

## 개발·검증

```bash
python -m unittest discover -s tests -v
python -m examples.run all
python -m examples.run_integrated
```

현재 통합 scaffold는 v0.3 plugin mode를 등록합니다. Summary S1을 upstream Runtime에 자동 등록하거나 실제 API·모델 서비스를 구성하지 않으므로 별도 연결 작업이 필요합니다.
