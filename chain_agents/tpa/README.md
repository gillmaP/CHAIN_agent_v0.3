# tPA Decision Support 프로토타입 · JLK 통합 안내

v0.3의 scoped Fact를 읽어 12개 검토 항목과 체중 기반 예상 용량을 계산합니다.
JLK 통합 백엔드가 Orchestrator에 등록해 사용하는 **동기 Python plugin**입니다.
Python 3.11 이상, 표준 라이브러리만 사용하며 API 키나 추가 설치가 필요 없습니다.
현재 LLM·병원 API 직접 호출·독립 HTTP 서버는 없습니다.

| 항목 | 현재 값 |
|---|---|
| 팀 브랜치 | `feature/tpa-rules` |
| 공개 진입점 | `chain_agents.tpa.agent:invoke` |
| Orchestrator 별칭 / Agent ID | `tpa_decision_support` / `tpa-decision-support-agent` |
| mode | `interim`, `final` |
| 도메인 출력 | `mode`, `evidence_package`, `assessment`, `mock_only` |
| assessment 제안 schema | `chain-tpa-assessment/prototype-v1` |
| 규칙 버전 | `tpa-rules-prototype-0.1.0` |
| 통합 사본 생성 스크립트의 Agent 버전 | `0.1.0-starter` — 운영 등록 버전은 공동 검토 후 결정 |

## 실행 방법

아래 명령은 **이 저장소 루트**에서 실행합니다. 저장소 접근 권한이 있는 환경이라면:

```bash
git clone --branch feature/tpa-rules https://github.com/gillmaP/CHAIN_agent_v0.3.git
cd CHAIN_agent_v0.3
python --version
```

이미 clone한 경우 해당 checkout에서 `git switch feature/tpa-rules` 후 실행합니다.
Windows에서 Python 명령이 `py`라면 아래 `python`을 `py -3.12` 등 설치된 3.11 이상 버전으로 바꿉니다.
단독 데모·테스트에는 Temporal이나 추가 패키지가 필요 없습니다.

```bash
python -m chain_agents.tpa.demo interim
python -m chain_agents.tpa.demo final
python -m chain_agents.tpa.demo high-bp
python -m chain_agents.tpa.demo low-platelets
python -m examples.run all
python -m unittest discover -s tests -v
```

`examples.run`의 기존 age-only 입력도 미확보 자료를 표시하며 실행됩니다.
`chain_agents.tpa.demo`는 13개 Fact를 명시적으로 만든 합성 사례입니다.
생성한 실행 JSON, 원천 병원 자료, 실제 환자 정보는 커밋하지 않습니다.

| 데모 | 예상 assessment.status | 확인할 동작 |
|---|---|---|
| `interim` | `INCOMPLETE_PENDING_DATA` | CT 전, 혈소판·INR·NIHSS 미확보 표시 |
| `final` | `PHYSICIAN_REVIEW_REQUIRED` | 검사 자료 확보 후에도 CT 판독·의료진 확인 필요 |
| `high-bp` | `PHYSICIAN_REVIEW_REQUIRED` | 190/94 mmHg → 혈압 항목 의료진 검토 |
| `low-platelets` | `BLOCKING_FINDING_IDENTIFIED` | 90,000/µL → 혈소판 규칙 미충족 소견 |

## 직접 호출 예제

JLK의 통합 호출은 Registry를 통한 Runtime 호출을 사용합니다. 아래는 함수와 전체 입력/출력을 확인하는 **독립 합성 예제**입니다.
저장소 루트에서 Python으로 실행할 수 있습니다.

```python
import json
from types import SimpleNamespace
from chain_agents.tpa.agent import invoke
from chain_agents.tpa.demo import sample

request, snapshot = sample(mode="final")
services = SimpleNamespace()  # 현재 tPA는 services를 사용하지 않음
output = invoke(request, snapshot, services)

print(json.dumps({"request": request, "snapshot": snapshot, "output": output},
                 ensure_ascii=False, indent=2))
assert output["assessment"]["status"] == "PHYSICIAN_REVIEW_REQUIRED"
assert output["evidence_package"] == snapshot["facts"]
```

`sample()`의 시각·식별자는 합성이며 평가 시각도 고정됩니다. 데모의 `manifest_hash`는 0으로 채운 placeholder입니다.
이 예제를 실제 Worker 요청으로 보내면 등록 hash 검증을 통과하지 못합니다. 실제 request·snapshot ID·dependencies·manifest hash는
등록된 Orchestrator/Runtime이 현재 자료와 설치 manifest로 생성·검증해야 합니다.

## 입력 형식

```python
def invoke(request: dict, snapshot: dict, services) -> dict:
    ...
```

입력은 v0.3 계약입니다. 전체 wire 검증은 upstream Runtime이 수행하고, tPA는 mode·Snapshot 연결·scope·자료 시각과 수치 등을 추가 확인합니다.
관련 공통 계약은 [docs/CONTRACT.md](../../docs/CONTRACT.md)입니다.

### request

| 필드 | 형식·의미 |
|---|---|
| `contract_schema` | `chain-agent-request/v0.3` |
| `request_id` | 호출 식별자 문자열 |
| `agent_id` | `tpa-decision-support-agent` |
| `agent_version` | Catalog/Registry/Policy에 등록된 동일한 버전 |
| `manifest_hash` | 등록된 설치 manifest의 `sha256:...` |
| `mode` | `interim` 또는 `final`; 작업 단계이며 치료 승인 상태가 아님 |
| `input_snapshot_id` | `snapshot.snapshot_id`와 동일 |
| `scope` | 전달할 Fact 이름의 문자열 배열; `snapshot.facts` key 집합과 정확히 일치 |
| `dependencies` | 실제 입력 근거의 Field reference 배열 |
| `evaluated_at` | 시간대가 있는 ISO8601 평가 시각 |

### snapshot 및 Fact

Snapshot은 `contract_schema: chain-context/v0.3`, `snapshot_id`, `known_at`, `facts`를 갖습니다.
`facts`는 이름 → Fact 객체의 dict입니다. 값만 보내거나 출처·상태를 생략하면 올바른 입력이 아닙니다.
환자 ID는 별도 request 최상위 필드로 전달되지 않으므로 임의로 추가하지 않습니다.

아래는 합성 혈소판 Fact 하나의 형식 예시입니다.

```json
{
  "value": 214000,
  "status": "AVAILABLE",
  "unit": "/uL",
  "source_ref": {
    "system": "SYNTHETIC",
    "record_id": "TPA-DEMO-001",
    "version": 1,
    "field": "platelet_count"
  },
  "source_time": "2026-10-06T15:36:00+09:00",
  "known_at": "2026-10-06T15:36:00+09:00"
}
```

Fact 필수 필드는 `value`, `status`, `source_ref`, `source_time`, `known_at`입니다.
`source_ref`는 `system`, `record_id`, `version`, `field`를 포함합니다.
선택 metadata인 `unit`, `confirmation_status`, `dependencies`도 입력 그대로 보존합니다.
미확보는 `value: null`과 해당 상태로 표현합니다. `false`나 `0`을 결측으로 치환하지 않습니다.
사용 가능한 상태는 `AVAILABLE`, `CONFIRMED`, `CONSISTENT`, `PRESENT`이며,
그 외 상태는 근거에 보존하되 남아 있는 수치를 평가에 쓰지 않습니다.

### 기본 scope와 단위

현재 upstream의 interim/final scope는 아래 13개 Fact입니다.

| Fact 이름 | 값 형식·단위 | 용도 |
|---|---|---|
| `lkw` | 시간대 포함 ISO8601 문자열 | 마지막 정상 확인 이후 경과 시간 |
| `ncct_completed` | boolean | NCCT 촬영 완료 여부; 출혈 판독이 아님 |
| `ncct_order_id`, `ct_order_id` | 문자열, 미확보 시 null | 촬영과 오더의 일치 확인 |
| `platelet_count` | 수치 + `/uL`, `10^3/uL`, `10^9/L` 등 지원 단위 | 혈소판 기준 비교·단위 정규화 |
| `inr` | 양수 수치, 무차원 | INR 항목 검토 |
| `anticoagulant` | 구조화 값·상태·확인 metadata | 노출 여부와 의료진 확인 필요 표시 |
| `weight_kg` | kg 수치; unit은 생략 또는 `kg` | 용량 산술 |
| `nihss` | 0–42 정수 | 참고 정보 |
| `sbp`, `dbp` | 양수 수치 + `mmHg` | 수축기·이완기 혈압 |
| `glucose` | 수치 + `mg/dL` 또는 `mmol/L` | 혈당 단위 정규화·목업 범위 검토 |
| `age` | 0–130 정수 | 연령 정보 |

단위가 필요한 검사에서 단위가 없거나 지원하지 않으면 값을 추정하지 않고 검토 필요로 표시합니다.
기본 필수 자료 목록과 임계값은 [policy.py](policy.py), 단위 처리는 [rules.py](rules.py)에 있습니다.
최근 수술/출혈·과거 뇌졸중·항혈소판제 등 기본 scope 밖 항목은 `NOT_IN_SCOPE`입니다.
추가 자료를 사용하려면 upstream scope와 Fact 이름 계약을 함께 확장해야 합니다.

## 출력 형식과 UI 연결

함수는 **도메인 dict**만 반환하며 최상위 key는 아래 4개로 고정합니다.

| key | 형식·의미 |
|---|---|
| `mode` | 요청의 `interim` / `final` |
| `evidence_package` | `snapshot.facts`와 값이 같은 독립 복사본 |
| `assessment` | 아래 schema의 구조화 객체 제안 |
| `mock_only` | 항상 `true` |

`assessment` 안의 주요 값은 다음과 같습니다. 배열 내부의 정확한 형식·enum은 [ASSESSMENT.md](ASSESSMENT.md)를 참고하세요.

```text
schema: chain-tpa-assessment/prototype-v1
rule_set: tpa-rules-prototype-0.1.0
status: BLOCKING_FINDING_IDENTIFIED | INCOMPLETE_PENDING_DATA | PHYSICIAN_REVIEW_REQUIRED
checks[]: check_id, label, result, value, detail, evidence[], source_ids[]
missing_information[]: 기본 필수 Fact 중 미확보 이름
scope_gaps[]: 평가 범위 밖 체크 ID
items_requiring_physician_confirmation[]: 확인이 필요한 체크 ID
dose_preview: weight_kg, options[], basis, evidence[], physician_confirmation_required,
              auto_order, auto_administration
limitations[]: 연구 범위와 미확정 사항
recommendation_type: DECISION_SUPPORT_ONLY
physician_decision_required: true
```

`checks`는 12개입니다. `missing_information`은 기본 필수 자료 목록이고 모든 PENDING 체크의 목록은 아닙니다.
미확보 항목이 없다고 전체 적응증/금기 평가가 완료된 것이 아닙니다. 화면은 `checks`, `scope_gaps`,
`items_requiring_physician_confirmation`도 함께 표시해야 합니다.

### Runtime 결과와 UI 조회 경로

Runtime은 도메인 dict를 `chain-agent-result/v0.3` envelope의 **`result`**에 넣습니다.
envelope의 `status: SUCCESS`는 프로그램 실행 성공이고, `assessment.status`는 검토 상태입니다.
두 상태를 치료 승인 여부로 해석하지 않습니다.

현재 upstream의 `snapshot` Query에서 수락된 최신 결과를 읽는 경로는 다음과 같습니다.
`handle`은 통합 백엔드가 Episode에 대응시켜 확보한 Temporal Workflow handle입니다.

```python
view = await handle.query("snapshot")
record = view.get("latest_results", {}).get("tpa_decision_support.final")
# 중간 평가 표시 시 key는 "tpa_decision_support.interim"
if record is not None:
    envelope = record["output"]
    if envelope["status"] == "SUCCESS":
        domain = envelope["result"]
        assessment = domain["assessment"]
        evidence = domain["evidence_package"]
```

`latest_results`는 수락된 결과를 담으며 실패·거절·실행 중 상태 전체를 대신하지 않습니다.
진행·실패 표시는 `agent_runs`, `pending_count`, `audit` 등 Orchestrator 조회 계약으로 처리합니다.
화면은 평가 mode, request ID, 입력 Snapshot ID, 평가 시각, `mock_only`와 근거 출처를 함께 연결합니다.

의료진 결정 화면은 최신 결과를 임의로 조합하지 않고,
`view["open_hitl"]["HITL_2_THROMBOLYSIS"]`의 `status == "OPEN"`인 기록의
**`request`, 고정 `snapshot`, `results`**를 사용합니다. 의료진 응답은 해당 요청 ID와 근거 ID에 연결해
백엔드가 `submit_decision` Signal로 전송합니다. tPA 모듈이 HITL 요청이나 치료 결정을 생성하지 않습니다.
자세한 UI/HITL 입력 계약은 [upstream README §5](https://github.com/donggunseo/chain-orchestrator-v03/blob/642f5b40525691912c685dda06043f79e37bcd1f/README.md#5-백엔드와-프론트엔드-연결)를 따릅니다.

### 입력 오류와 미확보 구분

- 정상 형식의 자료 미확보는 `PENDING`/`NOT_IN_SCOPE` 등을 포함한 도메인 결과로 반환합니다.
- 잘못된 mode, Snapshot 연결, scope, 수치·시각·오더 형식 등은 `ValueError`를 발생시킵니다.
- 현재 Runtime이 Agent 호출 중 `ValueError`를 잡으면 `status: FAILED`, `result: null`, `error: AGENT_INVALID_OUTPUT`으로 감쌉니다.
- Runtime의 사전 등록·hash·wire 검증 실패는 함수 호출 이전의 오류입니다. 실패 dict를 tPA의 정상 도메인 결과로 반환하지 않습니다.

## Orchestrator 등록과 호출 위치

연결 위치는 2026-10-08 확인한 upstream revision
[`642f5b40525691912c685dda06043f79e37bcd1f`](https://github.com/donggunseo/chain-orchestrator-v03/tree/642f5b40525691912c685dda06043f79e37bcd1f)를 기준으로 적었습니다.

```text
Workflow YAML: authorize_and_run(tpa_decision_support, mode)
  → Worker Activity: chain.run_agent_v03
  → AgentRuntime.invoke(job)
  → Registry entrypoint: chain_agents.tpa.agent:invoke
  → logic.run() → Facts / rules / dose
  → 도메인 dict → Runtime Result envelope
  → Engine 결과 검증·수락 → snapshot Query / HITL 고정 근거
```

현재 기본 흐름은 S2에서 새 근거마다 `interim`, 해당 NCCT 완료·오더 일치 후 S2_1에서 `final`을 호출합니다.
`final` 결과 수락 뒤 HITL #2가 열립니다. tPA의 결과 상태로 State를 직접 바꾸지 않습니다.

| 위치 | JLK 통합 시 연결·확인할 내용 |
|---|---|
| upstream `config/agents_v03.yaml` | `agents.tpa_decision_support`: Agent ID, version, implementation, modes, backend |
| upstream `config/workflow_v03.yaml` | S2/S2_1의 `authorize_and_run`, tPA `scopes`/`outputs`, `HITL_2_THROMBOLYSIS.after` |
| upstream `config/plugins.yaml` | 구현 entrypoint, 설치 파일 목록·hash, manifest hash, 검토 상태 |
| upstream `config/policy_v03.yaml` | 승인 버전, data_scopes/actions, HITL 규칙 |
| upstream `chain_demo/orchestration_activities.py` | `OrchestrationActivities.invoke`: `chain.run_agent_v03` Activity → Runtime |
| upstream `chain_demo/agents/runtime.py` | 등록 entrypoint import·호출, 공통 envelope 생성 |
| upstream `chain_demo/engine.py` | `_complete_agent`: 결과 수락·오래된 결과 거절; `snapshot`: 조회 반환 |
| upstream `chain_demo/temporal_workflow.py` | `snapshot` Query, `submit_event`/`submit_decision` Signal |
| 이 저장소 `chain_agents/tpa/agent.py` | 공개 동기 함수. JLK의 별도 Agent HTTP route 없이 plugin으로 호출 |

upstream 기본 tPA backend는 **fixture**입니다. 우리 구현을 사용하려면 Catalog의 implementation을
등록된 우리 plugin으로 바꾸고 backend는 **`kind: structured`**로 연결합니다.
`structured`는 Snapshot에서 직접 결과를 계산한다는 의미이며 외부 API가 자동 연결되는 설정이 아닙니다.
`entrypoint` 파일은 upstream 배포 root 안에 있어야 하므로 이 저장소의 `chain_agents/`를 포함합니다.
`pip install`만 하고 외부 위치의 모듈을 import하면 설치 검증과 맞지 않을 수 있습니다.

### 별도 통합 사본 생성

기존 [prepare_integration.py](../../scripts/prepare_integration.py)는 세 팀 plugin과 등록 설정을 **새 사본**에 연결합니다.
아래 경로는 예시이며 upstream checkout과 output은 실제 위치로 바꿉니다. output은 아직 없는 형제 폴더여야 합니다.
단일 줄 명령이므로 PowerShell에서도 같은 형태로 실행할 수 있습니다.

```bash
# 이 저장소 루트: upstream 의존성은 전체 연결 검증 때만 필요
python -m pip install -r ../chain-orchestrator-v03/requirements.txt
python scripts/prepare_integration.py --upstream ../chain-orchestrator-v03 --output ../chain-integration-demo --synthetic-demo
```

생성 사본의 tPA 연결 값은 `implementation: starter-tpa`,
`entrypoint: chain_agents.tpa.agent:invoke`, `agent_version: 0.1.0-starter`, `backend.kind: structured`입니다.
Catalog/Registry/Policy와 합성 fixture 버전 사본을 함께 맞추며 코드 파일 hash를 계산합니다.
Workflow의 임상 분기는 바꾸지 않습니다. 다른 팀의 결과물도 통합할 경우 각 팀의 검토된 코드를 먼저 포함한 뒤 설정을 생성해야 합니다.

생성 사본 루트에서 설정·설치 확인:

```bash
cd ../chain-integration-demo
python -c "from chain_demo.orchestration_config import load_orchestration_bundle; from chain_demo.agents.runtime import AgentRuntime; c=load_orchestration_bundle(); AgentRuntime(c['agents']); print('CONFIGURATION_OK')"
```

설정 확인 후 별도로 전체 합성 local 데모를 실행할 수 있습니다. 실행마다 새 output 경로를 지정합니다.

```bash
python -m demo --backend local --test-mode --hitl recorded --recorded demo/scenarios/recorded_hitl.json --expected demo/scenarios/expected.json --run-timeout 180 --output-dir output/jlk-tpa-check-01
```

`--synthetic-demo`는 새 로컬 사본에서만 APPROVED 데모 설정을 생성합니다. 옵션을 생략하면 PENDING 초안이므로
실행 차단이 정상입니다. 실제 배포 승인과 구분하며, 운영에는 검토된 Agent 버전·설치 hash·Policy/Registry를 사용합니다.
전체 local/Temporal 및 UI 검증은 JLK의 최종 통합 구성에서 별도로 수행해야 합니다.

## Tool/API 연동 위치

현재 tPA는 전달받은 scoped Snapshot만 읽으며 `services`를 호출하지 않습니다.
`services`의 현재 upstream 구현에는 `cache`, `backend`만 있고 `api_client`/`llm`은 없습니다.
이 브랜치에는 호출 가능한 병원 endpoint나 API 키 설정이 없습니다.

### 병원 자료를 tPA 입력으로 연결

```text
EMR / 간호 / OCS / LIS / RIS-PACS / 수동 입력
  → 출처별 Adapter.publish() → Store에 자료 버전 보존
  → SourceIngress.receive() → submit_event Signal
  → Worker resolve_source() → Context 갱신
  → Orchestrator의 요청 scope로 Snapshot 생성 → tPA.invoke()
```

| API·기능 | upstream 연결 파일 |
|---|---|
| EMR 기록·NIHSS 등 | `chain_demo/adapters/emr.py` |
| 혈압·혈당·체중 등 간호 자료 | `chain_demo/adapters/nursing.py` |
| 혈소판·응고 검사 | `chain_demo/adapters/lis.py` |
| CT 오더 | `chain_demo/adapters/ocs.py` |
| NCCT 완료 관련 자료 | `chain_demo/adapters/ris_pacs.py` |
| 자료 버전 보존·조회 | `chain_demo/adapters/store.py`, `chain_demo/adapters/ingress.py` |
| 외부 입력 형식·Worker 조립 | `chain_demo/source_contracts.py`, `chain_demo/worker.py:create_worker()` |

실제 병원 API 응답을 출처 계약에 맞춰 변환하고 Store·Ingress를 통해 넣는 작업은 통합 계층의 역할입니다.
위 파일은 연결 위치이며 실제 병원 API가 이 tPA 브랜치에서 구현돼 있다는 뜻은 아닙니다.
상세 Event·원천자료 계약은 [upstream README §7](https://github.com/donggunseo/chain-orchestrator-v03/blob/642f5b40525691912c685dda06043f79e37bcd1f/README.md#7-병원-apiapi-tool-연결)를 참고하세요.

### 향후 tPA에서 직접 읽기 API가 필요한 경우

API 명세·허용 식별자·scope·자료 출처 반환 계약을 먼저 합의합니다. request에 환자 ID가 별도로 없으므로
`request_id`를 환자 ID로 사용하거나 임의로 전체 차트를 조회하지 않습니다.
팀 폴더 안에 client/helper를 추가하고 `logic.py`의 Activity 호출 경계에서 연결할 수 있지만,
평가 함수인 `rules.py`/`dose.py`는 I/O 없는 계산으로 유지합니다.
주입형 client를 사용한다면 upstream `agents/services.py`의 `AgentServices`와
`agents/runtime.py`의 서비스 생성 코드도 함께 확장해야 합니다.
추가 client·프롬프트·모델 의존 파일은 Registry.files와 manifest hash에 반영합니다.
권한·timeout·실패·재시도 정책과 의존성을 조율하고 인증 정보는 코드·YAML 밖에서 주입합니다.

현재 upstream에는 독립 Tool Registry나 Workflow의 `call_tool` Action이 없습니다.
`tools:`/`call_tool`/`kind: api`/`url`을 YAML에 임의로 추가하는 방법은 지원하지 않습니다.
외부 I/O는 Worker Activity 또는 Adapter 경계에 둡니다.
[upstream README §9.7](https://github.com/donggunseo/chain-orchestrator-v03/blob/642f5b40525691912c685dda06043f79e37bcd1f/README.md#97-새-tool외부-api를-추가할-때)가 확장 범위를 설명합니다.

## JLK 통합 확인 목록

1. `assessment` 문자열 → 객체 제안의 소비자 schema·enum을 합의하고 UI가 필드를 구조적으로 표시하는지 확인.
2. 검토된 각 팀 plugin을 upstream 배포 root에 포함하고 entrypoint·Catalog·Registry·Policy·파일 hash·버전을 일치시킴.
3. tPA `backend.kind: structured`, interim/final의 13개 scope와 정확한 4개 outputs를 확인.
4. 병원 Adapter의 값·단위·status·version·시각을 확인하고 정정/철회 자료가 올바르게 재평가되는지 확인.
5. UI에서 실행 SUCCESS와 임상 검토 상태를 구분하고 미확보·범위 밖·의료진 확인·근거·용량 미리보기를 표시.
6. HITL #2의 고정 근거와 의료진 응답을 연결하고 실패·늦은 결과·재요청을 최종 통합 구성에서 검증.

2026-10-08 README 갱신 시 전체 단위 테스트 54개, 문서의 직접 호출 예제·CLI 4사례,
upstream revision `642f5b40525691912c685dda06043f79e37bcd1f`의 request/result wire validator와 출력 key 검사를 확인했습니다.
연동 위치도 해당 코드를 다시 읽어 확인했습니다. 이 검증은 전체 Temporal/UI 연동 성공을 의미하지 않습니다.

## 구현 구조

| 파일 | 책임 |
|---|---|
| `agent.py` | 기존 `invoke(request, snapshot, services)` 진입점 |
| `logic.py` | 공통 입력 경계 확인, 복사된 Fact와 도메인 결과 조합 |
| `facts.py` | 시각·수치 확인과 원본 출처를 보존하는 조회 |
| `rules.py` | I/O 없는 개별 체크 함수 |
| `dose.py` | Decimal 기반 용량 산술과 표시 반올림 |
| `policy.py` | 변경 불가능한 연구용 임계값과 한계 |
| `demo.py` | 합성 입력과 CLI 시연 |

Agent는 scope 밖의 자료를 조회하거나 LLM으로 값을 추론하지 않습니다.
입력 객체를 바꾸지 않으며 `services` 호출, 네트워크, 파일 쓰기, 상태전이를 하지 않습니다.
Runtime이 SUCCESS/FAILED envelope, 등록·hash 검증, 감사 기록을 맡고,
Orchestrator와 의료진이 HITL·알림·치료 결정을 수행합니다.

## 출력과 검토 대상

최상위 키는 기존과 같은 `mode`, `evidence_package`, `assessment`, `mock_only` 4개입니다.
`evidence_package == snapshot.facts`를 유지하고 `mock_only=True`를 명시합니다.

**이 브랜치는 `assessment`를 기존 문자열에서 구조화된 객체로 확장하는 제안입니다.**
공통 파일, Workflow 출력 목록, 등록 버전은 수정하지 않았습니다.
현재 upstream의 JSON wire validator와 출력 key 검사는 객체도 수용하지만,
문자열을 기대하는 Console/다른 소비자는 함께 검토·수정해야 합니다.
팀 검토와 등록 버전/hash 갱신 후 통합하세요. 기존 계약과 완전히 같은 결과 타입이라고
주장하지 않습니다. 자세한 제안은 [ASSESSMENT.md](ASSESSMENT.md)에 있습니다.

## 주요 동작

- 4.5시간 일반 경로 밖은 전문의 검토로 표시합니다. 선별 영상 기반 연장 경로를 자동 제외하지 않습니다.
- NCCT 완료와 오더 일치를 확인하되, 촬영 완료를 출혈 없음 판독으로 해석하지 않습니다.
- 혈소판·INR 수치, 혈압·혈당 단위, 자료 시각을 확인합니다.
- 혈압 5분 재확인은 데모 정책, 혈당 50–400은 기존 목업 기준입니다.
- 항응고제 노출은 약제·복용 시각·신기능·특이 검사 검토 대상으로 표시합니다.
- `NO_EVIDENCE`와 확인된 복용 없음은 구분하며, 고령·NIHSS·아스피린만으로 자동 제외하지 않습니다.
- PENDING/CONFLICT/ERROR/RETRACTED/INVALIDATED 등은 남아 있는 수치를 사용하지 않습니다.
- 기본 scope에 없는 수술·출혈·과거 뇌졸중·항혈소판제는 `NOT_IN_SCOPE`로 표시하고 출처를 만들지 않습니다.
- 체중이 없으면 예상 용량 options는 빈 배열입니다. 단위가 없거나 불명확한 검사는 추정하지 않습니다.
- 잘못된 수치·시각·오더 자료는 `ValueError`로 실패하며 정상 결과에 오류 객체를 넣지 않습니다.

예상 용량은 처방·투약 승인이 아닙니다. 합성 67 kg 사례는 alteplase 60.3 mg
(bolus 6.03 / infusion 54.27), TNK 16.75 mg이고 최대량은 각각 90 / 25 mg입니다.
Decimal 계산값과 0.1 mg 단위 ROUND_HALF_UP 표시값을 구분합니다.

이 프로토타입은 전체 IVT 적응증·금기 검토나 임상 검증을 대체하지 않습니다.
현재 scope로는 disabling deficit, 출혈 판독, 최근 수술/외상·활동성 출혈 등 주요 자료를
확정할 수 없으므로, 확보된 자료가 모두 있어도
최종 상태는 `PHYSICIAN_REVIEW_REQUIRED`입니다. 병원 승인 프로토콜 원문은 제공되지 않았습니다.

근거와 확인 범위는 [SOURCES.md](SOURCES.md)를 참고하세요.
