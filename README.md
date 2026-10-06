# CHAIN Agent Starter

## 1. 바로 실행

Python 3.11 이상. 기본 예제와 단위 테스트는 추가 설치 없이 동작합니다.

```bash
python -m examples.run all
python -m examples.run screening
python -m examples.run summary
python -m examples.run tpa
python -m unittest discover -s tests -v
```

`examples/` 입력과 Screening 답은 명시적으로 만든 합성 테스트 데이터입니다. 예제의 POSITIVE는 모델 예측이 아닙니다.

## 2. 각 팀이 수정할 곳

| 팀 | 기능을 넣을 파일 | 팀별 테스트 | 현재 baseline |
|---|---|---|---|
| 1: Stroke Screening | `chain_agents/screening/logic.py` | `tests/test_screening.py` | 합성 fixture 응답. backend가 없으면 명시적 실패 |
| 2: Clinical Summary | `chain_agents/summary/logic.py` | `tests/test_summary.py` | 요청 Fact 보존 + 누락 목록 + 캐시 |
| 3: tPA Decision Support | `chain_agents/tpa/logic.py` | `tests/test_tpa.py` | 요청 Fact를 evidence_package로 반환 |

`agent.py`는 공통 호출 규격을 유지하는 진입점입니다. 각 폴더에 `extractor.py`, `rules.py`, `prompts/` 등을 필요할 때 추가하세요. 아직 LLM, 임상 판정 규칙, 용량 계산은 없습니다.

| 공통 파일 | 역할 |
|---|---|
| `chain_agents/common.py` | 최소한의 입력 경계 검사, hash, 결측 처리 |
| `examples/support.py` | 로컬 테스트용 cache/fixture service |
| `scripts/prepare_integration.py` | upstream 별도 사본에 모듈과 Registry/config 연결 |
| `.github/workflows/tests.yml` | push/PR마다 Python 3.11·3.12 테스트 |
| `docs/CONTRACT.md` | 입력·출력 및 Summary 제약 |
| `docs/INTEGRATION.md` | 오케스트레이터 연결과 승인 구분 |
| `AGENTS.md` | 세 팀 공통 변경 규칙 |

## 3. 모든 Agent는 같은 함수 형태

```python
def invoke(request, snapshot, services) -> dict:
    # request: mode, scope, evaluated_at, snapshot ID 등
    # snapshot["facts"]: 요청 범위의 값·상태·출처·버전·시각
    # services.cache / services.backend: 실행 환경이 주입
    return domain_result
```

함수는 **도메인 결과 dict만 반환**합니다. 공통 SUCCESS/FAILED envelope, 상태전이, HITL, 이벤트, 알림은 upstream Runtime/Orchestrator가 처리합니다. 실패는 `ValueError`로 알립니다. 오류 dict를 정상 반환하면 SUCCESS로 감싸질 수 있습니다.

### 결과의 정확한 key

| Agent | mode | 반환 key |
|---|---|---|
| Screening | `screening` | `screening_result`, `mock_only`, `basis` |
| Summary | `context` | `structured_context`, `missing_information`, `cache` |
| tPA | `interim`, `final` | `mode`, `evidence_package`, `assessment`, `mock_only` |

새 key를 추가하거나 `mock_only`를 제거하려면 upstream Workflow의 `outputs`, 사용하는 분기와 구현 버전을 함께 변경해야 합니다.

**Summary의 중요 제약:** 현재 upstream 엔진은 `structured_context == snapshot.facts`를 검사합니다. 자유로운 LLM 요약이나 새 임상 Fact를 그 안에 넣을 수 없습니다. 임상 extraction 결과를 어디에 반영할지 오케스트레이션 팀과 별도 출력 계약을 정해야 합니다. 우선 baseline에서는 원본 Fact를 그대로 보존합니다.

## 4. 팀별 개발 순서

1. 예제 실행으로 request/snapshot/result 형태 확인.
2. 팀의 `logic.py`에 기능을 추가하고 helper도 같은 팀 폴더에 배치.
3. 팀 테스트에 새 합성 입력과 기대 결과 추가.
4. 계약이 유지되는지 전체 테스트 실행 후 PR.
5. upstream 통합 사본에서 검증하고, 검토된 코드·버전·hash로 배포 등록.

브랜치 예: `feature/screening-extraction`, `feature/summary-extraction`, `feature/tpa-rules`.
`common.py`, 출력 계약, 통합 스크립트는 세 팀 공동 검토 대상으로 두세요. 모델 선택 전 공통 LLM client를 미리 고정할 필요는 없습니다.

## 5. 오케스트레이터 연결

기본 개발은 Temporal 없이 가능합니다. 전체 연결 검증만 upstream 의존성이 필요합니다.
원본 checkout을 변경하지 않고 **새 형제 폴더**에 통합 사본을 만듭니다.

```bash
# parent/
#   chain-agent-starter/       이 저장소
#   chain-orchestrator-v03/    공유받은 upstream clone

python -m pip install -r ../chain-orchestrator-v03/requirements.txt
python scripts/prepare_integration.py \
  --upstream ../chain-orchestrator-v03 \
  --output ../chain-integration-demo \
  --synthetic-demo
```

새 사본에는 세 plugin, 대응하는 Catalog/Registry/Policy, 새 버전에 맞춘 **합성 fixture 사본**이 생성됩니다. 원본 코드는 유지되며 임상 흐름 YAML은 바꾸지 않습니다. `--synthetic-demo`의 APPROVED는 이 로컬 합성 데모 설정에만 해당합니다. 옵션을 생략하면 Registry는 PENDING인 검토용 초안이고 실행이 차단됩니다. 실제 환경의 승인 상태는 자동 변경하지 않습니다.

통합 검증 명령은 [docs/INTEGRATION.md](docs/INTEGRATION.md)를 보세요.

## 6. 테스트 범위

입력 보존, scope/snapshot binding, mock 출력, false/0/null 구분, conflict/error/retracted 상태, cache 재사용과 snapshot 변경을 검사합니다. upstream과 같은 key 계약을 유지하되, Summary/tPA는 ERROR·RETRACTED·INVALIDATED도 미확보로 취급합니다.

로컬 helper는 upstream의 전체 wire validator를 재구현하지 않습니다. 실제 Runtime은 hash, 시간, dependencies, Registry를 먼저 검증합니다. 이 테스트 통과는 임상 성능이나 운영 배포 승인을 의미하지 않습니다.

## 7. GitHub 협업

이 폴더 자체가 공유 저장소의 루트가 되도록 올리면 됩니다. GitHub Actions와 팀별 테스트가 포함되어 있습니다. 원천 병원 자료·실제 환자 정보·API 키는 커밋하지 마세요. 저장소 소유자/팀 GitHub 계정이 정해지면 팀별 CODEOWNERS를 추가하면 됩니다.
