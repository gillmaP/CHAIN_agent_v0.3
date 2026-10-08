# 오케스트레이터 연결

## 설치 구조

upstream Registry는 entrypoint의 실제 파일이 **프로젝트 root 내부**에 있어야 한다고 검사합니다. 외부 pip 패키지를 설치하는 것만으로 연결되지 않습니다. 이 starter의 `chain_agents/`를 upstream 배포 root 안에 포함해야 합니다. `prepare_integration.py`는 이 작업을 별도 사본에서 수행합니다.

| alias | entrypoint | backend |
|---|---|---|
| stroke_screening | `chain_agents.screening.agent:invoke` | fixture |
| clinical_summary | `chain_agents.summary.agent:invoke` | structured |
| tpa_decision_support | `chain_agents.tpa.agent:invoke` | structured |

각 manifest는 공통 파일과 해당 팀 폴더의 Python 파일 hash를 포함합니다. Screening은 합성 fixture 파일도 포함합니다. 공유 helper를 추가하거나 모델 파일/프롬프트에 의존하면 해당 파일을 manifest에 추가해야 합니다. 해시를 맞추는 일과 실제 승인 절차는 별개입니다.

## 합성 데모 사본 생성

starter 루트에서:

upstream checkout은 파일 바이트 hash가 보존되도록 줄바꿈 자동 변환 없이 받습니다.

```bash
git -c core.autocrlf=false clone https://github.com/donggunseo/chain-orchestrator-v03.git ../chain-orchestrator-v03
```

```bash
python scripts/prepare_integration.py --upstream ../chain-orchestrator-v03 \
  --output ../chain-integration-demo --synthetic-demo
```

- 원본 checkout과 기존 출력 폴더를 덮어쓰지 않습니다.
- 새 Agent 버전 `0.1.0-starter`, 새 구현 ID `starter-screening/summary/tpa`를 사용합니다.
- 기존 fixture 파일은 변경하지 않습니다. `starter_fixtures/`에 사본을 만들고 해당 사본의 agent_version만 바꿉니다.
- 새 사본의 Catalog/Registry/Policy만 연결합니다. Workflow의 임상 분기는 그대로입니다.
- `--synthetic-demo`가 없으면 PENDING 초안이므로 다음 로딩은 승인 오류로 차단되는 것이 정상입니다.

## 설정 검증

새 통합 사본의 root에서:

```bash
python - <<'PY'
from chain_demo.orchestration_config import load_orchestration_bundle
from chain_demo.agents.runtime import AgentRuntime
configuration = load_orchestration_bundle()
AgentRuntime(configuration['agents'])
print('CONFIGURATION_OK')
PY
```

## 로컬 엔진 전체 데모

upstream requirements를 설치한 환경에서 실행합니다. `--backend local`도 Temporal SDK를 import하지만 별도 Temporal 서버는 필요 없습니다.

Windows에서는 WSL/Linux 환경에서 아래 전체 데모를 실행합니다. 확인한 upstream
`642f5b40525691912c685dda06043f79e37bcd1f`의 FixtureBackend는 파일 허용 목록과 비교할 때
OS별 경로 문자열을 사용해서 Windows에서 Screening이 `FIXTURE_NOT_INSTALLED`로 실패합니다.
생성 manifest 경로는 `/`로 통일했으며, tPA의 structured Runtime 호출은 Windows에서도 확인했습니다.

```bash
python -m demo --backend local --test-mode --hitl recorded \
  --recorded demo/scenarios/recorded_hitl.json \
  --expected demo/scenarios/expected.json \
  --run-timeout 180 --output-dir output/starter-check-01
```

`outcome.json`에서 실행 결과를 확인합니다. 매번 새 output 경로를 사용하세요. 테스트 결과는 [VALIDATION.md](VALIDATION.md)에 기록합니다.

Temporal 서버를 사용하는 테스트와 실제 병원 시스템 연동은 별도입니다. Local Engine 성공을 Temporal History Replay 성공으로 표현하지 않습니다.

## 실제 팀 구현으로 교체

`logic.py`를 구현한 다음 해당 팀의 backend/outputs/version을 조율합니다. Screening이 더 이상 fixture를 사용하지 않으면 backend를 structured로 변경하고 모델 client를 팀 모듈에서 호출합니다. 새 결과 key가 생기면 Workflow outputs와 결과 소비 코드를 같이 변경합니다. 변경한 코드/프롬프트/helper가 설치 manifest에 포함되는지 확인하고 Registry/Policy 승인을 받습니다.
