# CHAIN Agents

Stroke Screening, Clinical Summary, tPA 의사결정지원 Agent의 개발 저장소입니다.
공통 Python 진입점은 `invoke(request, snapshot, services) -> dict`입니다.

## Clinical Summary

S1 요청을 받아 약물·과거력·LKW 정보를 추출하고 근거와 함께 반환합니다.
HTTP 실행, 비동기 상태 조회, SQLite 저장, 최근 성공 결과 조회를 제공합니다.

- **[Summary README](chain_agents/summary/README.md)** — 빠른 시작, 실제 모델 실행, API, Orchestrator·Tool 연결
- **[입출력 계약](chain_agents/summary/CONTRACT.md)** — 질문, 상태·값, 인용, 시간, 상충 규칙

```bash
# 저장소 루트 / Python 3.11+ / GPU 없는 합성 데모
python -m chain_agents.summary.api_service \
  --demo --port 8091 --store-root /data/data2/chain-summary/demo
```

합성 데모는 API 연결 확인용입니다. 실제 모델 실행과 자료 연결은 Summary README를 참고하세요.

## 저장소 구성

| 경로 | 역할 |
|---|---|
| `chain_agents/screening/` | Screening starter: 합성 fixture 응답 |
| `chain_agents/summary/` | S1 임상정보 추출 + 기존 Context 보존 경로 |
| `chain_agents/tpa/` | tPA starter: 근거 패키지 반환 |
| `chain_agents/common.py` | 공통 입력 경계 검사 |
| `examples/` | 세 Agent의 기본 snapshot 호출 예제 |
| `tests/` | 공통·팀별 회귀 테스트 |
| `scripts/prepare_integration.py` | 공유 오케스트레이터의 별도 통합 사본 생성 |
| `docs/` | 기존 v0.3 공통 계약·통합 안내 |

## 기본 예제와 테스트

```bash
python -m examples.run all
python -m unittest discover -s tests -v
```

`examples.run summary`는 기존 snapshot/Context 예제입니다.
S1 자료 조회·LLM·HTTP 예제는 위 Summary README의 명령을 사용합니다.

## 오케스트레이터 연결

| 경로 | 입력 | 도메인 출력 |
|---|---|---|
| Screening `screening` | request + snapshot | `screening_result`, `mock_only`, `basis` |
| Summary `context` | request + snapshot | `structured_context`, `missing_information`, `cache` |
| Summary S1 | 자료 참조 + 질문, `snapshot=None` | 질문별 `items`, 미확인 정보 등 |
| tPA `interim/final` | request + snapshot | `mode`, `evidence_package`, `assessment`, `mock_only` |

공유 v0.3의 Summary Context는 원천 `snapshot.facts`를 그대로 보존합니다.
S1 임상 추출의 출력 계약은 별도이며, mode/Agent 등록과 UI·후속 Agent 연결은 통합팀과 맞춰야 합니다.
워크플로 상태 전이, HITL, 실행 인가, 이벤트는 오케스트레이터가 담당합니다.

기존 snapshot 통합 절차는 [공통 계약](docs/CONTRACT.md)과 [통합 안내](docs/INTEGRATION.md)에 있습니다.
이 문서들을 S1 HTTP 계약과 혼용하지 마세요.

## 개발 규칙

각 팀은 해당 Agent 폴더와 팀별 테스트를 관리합니다. 공통 계약·출력 변경은 통합 검토 대상입니다.
작업 규칙은 [AGENTS.md](AGENTS.md)를 따릅니다.
환자 자료·인증 정보·모델 가중치·실행 결과는 Git에 포함하지 않습니다.
Summary 실행 자료와 모델은 `/data/data2` 또는 `/data/data3`에 저장합니다.
