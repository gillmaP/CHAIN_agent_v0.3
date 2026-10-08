# CHAIN Agents

Stroke Screening, Clinical Summary, tPA 의사결정지원 모듈을 개발하는 공유 저장소입니다.
각 Agent는 요청과 허용된 자료를 처리해 결과 dict를 반환합니다. 실행 제어·상태 전이·HITL·알림은
Orchestrator/Runtime과 연결합니다.

## 1. 빠른 시작

Python 3.11 이상, 저장소 루트에서 실행합니다.

```bash
# 공통 v0.3 계약의 합성 baseline 예제
python -m examples.run all

# Summary S1 모듈 예제 — 고정 합성 추출기, GPU 불필요
python -m examples.summary_s1
```

기본 예제 실행은 실제 LLM 성능 평가가 아닙니다.
실제 모델 실행 방법은 [Summary README](chain_agents/summary/README.md)를 참고하세요.

## 2. 팀별 코드

| Agent | 코드 | 개발 브랜치 | 안내 |
|---|---|---|---|
| Stroke Screening | `chain_agents/screening/` | `feature/screening` | [README](chain_agents/screening/README.md) |
| Clinical Summary | `chain_agents/summary/` | `feature/summary` | [README](chain_agents/summary/README.md) |
| tPA 의사결정지원 | `chain_agents/tpa/` | `feature/tpa-rules` | [README](chain_agents/tpa/README.md) |

이 브랜치에는 Summary 변경이 포함되어 있습니다. 다른 팀의 최신 구현이 자동으로 합쳐진 상태는 아닙니다.
위 링크는 현재 checkout의 파일을 가리킵니다. 다른 팀의 최신 구현은 해당 개발 브랜치에서 확인하세요.

```text
chain_agents/<agent>/   호출 진입점 · 도메인 처리 · 필요한 서비스 클라이언트
examples/               합성 입력과 최소 실행 예제
tests/                  Agent별 계약·처리 테스트
docs/                   공통 계약과 Orchestrator 연결 안내
```

## 3. 공통 호출 규칙

```python
def invoke(request, snapshot, services) -> dict:
    ...
```

- `request`: 작업 모드, 요청 범위, 기준 시각 등 계약에 정의된 입력.
- `snapshot`: 해당 호출에서 허용된 facts와 출처·상태·버전·시각.
- `services`: Runtime이 제공하는 cache, backend 또는 데이터 조회·추출 서비스.
- 반환: Agent별 도메인 결과. 실패를 정상 결과 dict로 감추지 않습니다.
- 공통 helper와 출력 계약 변경은 관련 팀 및 오케스트레이션 팀의 공동 검토 대상입니다.

| v0.3 Agent / mode | 기존 반환 key |
|---|---|
| Screening / `screening` | `screening_result`, `mock_only`, `basis` |
| Summary / `context` | `structured_context`, `missing_information`, `cache` |
| tPA / `interim`, `final` | `mode`, `evidence_package`, `assessment`, `mock_only` |

**Summary 신규 S1 경로는 별도 계약입니다.**
`chain_agents.summary.agent.invoke_s1(request, data_api=..., extractor=...)`는
`summary-s1-fields/v1`의 `items`를 반환합니다. 기존 context 경로의
`structured_context == snapshot.facts`는 유지합니다. 새 결과를 기존 Workflow에 그대로 넣지 말고
출력 계약·소비자·등록 버전을 합의해야 합니다.

## 4. Orchestrator 및 Tool/API 연결

```text
Orchestrator/Runtime → Agent 함수 → 도메인 결과 반환
                         ↑
                 주입된 자료 / 데이터 Tool 클라이언트
```

- 병원 EMR/OCS 직접 연결은 별도 데이터 제공 계층의 역할이며 현재 확정된 병원 연결은 없습니다.
- 가상 자료 제공자는 개발·통합 예제에 사용합니다. 실제 API 계약이 정해지면 제공자를 교체합니다.
- Agent는 요청 자료의 출처·환자·버전을 확인하고 자체 출력 계약을 검증합니다.
- 결과 저장·UI 조회·실행 ID·재시도·알림은 Runtime에서 연결할 책임과 경로를 확정해야 합니다.
- Summary는 독립 HTTP 서버나 SQLite 서비스 실행을 필수로 요구하지 않습니다.

공통 연결 안내: [INTEGRATION.md](docs/INTEGRATION.md), [CONTRACT.md](docs/CONTRACT.md).
기존 `scripts/prepare_integration.py`는 v0.3 plugin 통합 사본을 준비합니다.
신규 S1 추출 결과와 전체 UI 연결까지 완료하는 도구는 아닙니다.

## 5. 개발·공유

```bash
python -m unittest discover -s tests -v
```

소유 범위와 변경 규칙은 [AGENTS.md](AGENTS.md)를 따릅니다. 다른 Agent 코드는 해당 팀과 조율해 변경합니다.
모델 가중치, 환자 원문, 인증 정보, 실행 DB·로그·HTML 결과물은 Git에 저장하지 않습니다.
102 서버의 모델·실험 산출물은 `/data/data2` 또는 `/data/data3` 아래에 보관합니다.
Summary의 독립 서버·실험 도구는 통합 소스에서 분리해 별도 보관했습니다.
