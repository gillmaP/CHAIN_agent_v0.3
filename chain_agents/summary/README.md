# Clinical Summary Agent — S1 프로토타입

기준: 2026-10-08 확정한 `summary-s1-fields/v1`, GT `s1-gold-review-v2`, 추출 규칙 `s1-status-v2`.
서버 `166.104.110.102`, 컨테이너 `jhbak_ct`, 저장소 `/jhbak/CHAIN_agent_v0.3`, 브랜치 `feature/summary`.

## 무엇을 구현했는가

S1 최초 진입 때 요청받은 환자 자료를 읽고, 여섯 질문에 대한 **값·정보 상태·출처**를 반환한다.
구조화 자료는 Python 코드가 처리하고, 문서 원문은 내부 LLM이 한 번 읽어 근거와 답을 추출한다.
코드가 추출 결과를 검증한 뒤 같은 값의 근거를 합치고 상충은 보존한다.
치료 결정, 다음 Agent 호출, 알림, 워크플로 상태 변경은 이 Agent의 역할이 아니다.

**JLK 통합용 HTTP 실행·비동기 상태 조회·결과 저장/조회·Site Data API connector를 구현했다.**
시작 명령, curl 예시, 응답과 UI 연결은 **[API 통합 가이드](API_INTEGRATION.md)**를 먼저 읽는다.
도메인 `invoke`는 그대로이고 HTTP runner가 실행 metadata와 저장을 담당한다.
WG4 Safety Gate, Event Bus, 실제 병원 인증은 JLK 플랫폼 연동 대상이다.
외부 응답은 명시적 `clinical-summary-integration/v1` 프로필이며 원래 v0.12 스키마와 차이를 숨기지 않는다.

## 읽는 순서

0. **[JLK API 통합 가이드](API_INTEGRATION.md)**: 서버 시작, 호출·poll·조회, API 명세, 인증·CORS, Tool 경로.
1. [S1 전체 처리 흐름](S1_FLOW.md): 요청 → 조회 → 코드/LLM 처리 → 검증 → 반환 → 평가.
2. [현재 입출력 규칙](S1_TYPED_SUMMARY.md): 질문, 상태, 시간값, 근거, 상충 구조.
3. [Mock v0.12/PDF 대조](MOCK_V012_ALIGNMENT.md): 유지·변경·미구현과 연동 전 확인 사항.
4. [실제 입출력 예시](S1_EXAMPLES.md): Mock 원래 요청, 확정 실험 1번의 실제 LLM 입력/출력/최종 결과.
5. [정리 이력](CLEANUP_HISTORY.md): 퇴역한 실험 코드와 복구 위치.

## 호출과 의존성 주입

공개 함수는 `agent.invoke(request, snapshot, services) -> dict`다.

```python
from types import SimpleNamespace
from chain_agents.summary.agent import invoke

services = SimpleNamespace(
    summary_data_api=reader,      # get(relative_path) -> Python dict
    summary_extractor=extractor, # extract(documents, questions) -> facts/reviewed_documents
)
result = invoke(request, None, services)
```

`reader`와 `extractor`는 호출 측에서 실제 객체로 주입해야 한다. 위 코드는 인터페이스 설명이며 두 객체의 생성은 다음과 같다.
참조형 S1 호출의 `snapshot`은 반드시 `None`이다. `input_references` 없는 기존 v0.3 호출은
snapshot passthrough 분기로 가므로 두 입력 계약을 섞지 않는다.

```python
from pathlib import Path
from chain_agents.summary.experiment import MODELS
from chain_agents.summary.history_s1_extractor import LocalS1Extractor
from chain_agents.summary.mock_contract import FixtureDataAPI

# responses: GET 경로를 key로 하는 fixture dict. 실제 연결은 인증된 reader로 교체한다.
reader = FixtureDataAPI(responses)
model_key = 'gemma4_12b_it'
extractor = LocalS1Extractor(
    model_key,
    Path('/data/data2/jhbak/CHAIN_agent_summary_prototype/models') / MODELS[model_key]['directory'],
    gpu='3', method='direct', max_new_tokens=8192,
)
```

모델은 요청마다 새로 로딩하지 않고 worker에서 재사용한다. GPU 선택은 CUDA 초기화 전에 이루어져야 한다.
두 모델을 한 프로세스에서 GPU 환경변수만 바꾸어 번갈아 로딩하지 않는다.

## 요청 / 반환 형식

필수 항목은 `episode_id`, `encounter_id`, `patient_id`, `input_references`, `questions`다.
도메인 함수는 `trigger`를 검사하지 않지만 새 HTTP runner는 `trigger.state_enter=S1`을 검사한다.
실제 S1 상태와 실행 인가는 플랫폼 책임이다.

```json
{
  "episode_id": "EP-HYG-261006-058",
  "encounter_id": "E261006058",
  "patient_id": "PT-HYG-edd5a27af1",
  "trigger": {"state_enter": "S1", "cause_event_id": "EVT-HYG-261006-004874"},
  "input_references": [
    "medication:active", "condition:problem_list", "encounter_history:6m",
    "document:DOC-2610060412@1", "document:DOC-2610060403@2"
  ],
  "questions": ["anticoagulant_use", "recent_surgery_or_bleeding", "previous_stroke", "lkw_records"]
}
```

최종 반환은 `schema_version`, `episode_id`, `encounter_id`, `input_references`, `questions`,
`items`, `missing_information`, `model_info`, `mock_only`다. `items`는 질문별 객체의 **배열**이다.

```json
{
  "question": "anticoagulant_use",
  "status": "documented",
  "value": false,
  "evidence": [{"source_ref": "document:example@1", "quote": "현재 항응고제를 복용하지 않는다"}],
  "alternatives": []
}
```

위 item은 형식 설명용 합성 예시다. 다섯 key를 항상 둔다. `documented/false`는 명시적 부정,
`not_stated/null`은 언급 없음, `explicitly_unknown/null`은 명시적 미확인이다.
`conflicting/null`이면 서로 다른 값을 `alternatives`에 보존한다. 전체 실제 JSON은 [예시 문서](S1_EXAMPLES.md)에 있다.

## Orchestrator / Tool / API 연동 위치

| 접점 | 코드 / 계약 | 현재 상태 |
|---|---|---|
| Agent 실행 | `agent.py:invoke` → `logic.py:run` | Python 함수 호출 구현 |
| S1 처리 | `history_s1_summary.py:run_history` | 구현; 상태 전이 판단 없음 |
| 자료 조회 Tool | `services.summary_data_api.get(path)` | `FixtureDataAPI` 또는 `api_adapter.HTTPDataAPI` (bearer token·timeout·redirect 차단) |
| 경로·환자·문서 버전 확인 | `mock_contract.py:endpoint/resolve` | 구현 |
| 내부 LLM | `services.summary_extractor.extract` | 로컬 Transformers 추론 구현; LLM의 Tool 호출 없음 |
| 추출/최종 항목 검증 | `history_s1_contract.py` | 구현 |
| `POST /agents/clinical-summary-agent/invoke` | `api_service.make_server` | 동기/비동기 호출 구현 |
| 실행 토큰 / scope / timeout / 재시도 | PDF §8.1, §11 / Runtime | bearer 전달과 실패 timeout 구현; WG4 토큰 검증·scope·자동 재시도는 플랫폼 책임 |
| 저장 / 결과 URL / 완료 이벤트 | `api_service.Store` / JLK Event Bus | SQLite 저장·GET 결과 조회 구현; Bus 발행은 미구현 |
| 수락 전 검증 / Dashboard / HITL | Orchestrator / Console | 도메인 validator와 별개; 통합 미구현 |

현재 reader의 상대 경로는 PDF §7A와 같다.

| `input_references` | `GET` 상대 경로 |
|---|---|
| `medication:active` | `/patients/{patient_id}/medications?status=active` |
| `condition:problem_list` | `/patients/{patient_id}/conditions` |
| `encounter_history:6m` | `/patients/{patient_id}/encounters?months=6` |
| `document:{id}@{version}` | `/documents/{id}?version={version}` |

PDF의 base URL은 `https://sitenode.hyumc-guri.local/chain/api/v0.1`이라는 mock 주소다.
로컬 stub은 `http://localhost:8080/chain/api/v0.1`이며 prefix 생략도 지원한다.
`HTTPDataAPI`가 base URL·bearer token·HTTP timeout을 적용한다. 실행 토큰의 유효성과 scope는 Site Data API/게이트웨이가 검증해야 한다.
FHIR facade와 내부 LLM HTTP endpoint는 현재 경로에서 사용하지 않는다.

## 실행 방법

### 원래 Mock 요청 한 건을 실제 모델로 처리

아래는 서버에 이미 저장된 원안 fixture를 읽어 공개 `invoke`를 호출하는 예제다. 실행하면 GPU 3에서 Gemma 추론을 수행한다.
이번 문서화에서는 실행하지 않았다. 고정 응답을 주는 mock stub을 호출하는 예제가 아니다.

```bash
cd /jhbak/CHAIN_agent_v0.3
export PYTHONDONTWRITEBYTECODE=1
/data/data2/jhbak/CHAIN_agent_summary_prototype/runtime/gemma4-venv/bin/python - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from chain_agents.summary.agent import invoke
from chain_agents.summary.experiment import MODELS
from chain_agents.summary.mock_contract import FixtureDataAPI
from chain_agents.summary.history_s1_extractor import LocalS1Extractor

base = Path('/data/data2/jhbak/CHAIN_agent_summary_prototype')
files = base / 'datasets/mock_v012'
executions = json.loads((files / '05_agent_executions.json').read_text())
request = next(x['input'] for x in executions if x['key'] == 'summary')
responses = json.loads((files / '15_data_api_simple.json').read_text())
key = 'gemma4_12b_it'
extractor = LocalS1Extractor(key, base / 'models' / MODELS[key]['directory'],
                             gpu='3', method='direct', max_new_tokens=8192)
services = SimpleNamespace(summary_data_api=FixtureDataAPI(responses), summary_extractor=extractor)
result = invoke(request, None, services)
out = base / 'outputs' / datetime.now(timezone.utc).strftime('s1_mock_single_%Y%m%dT%H%M%S%fZ')
out.mkdir(parents=True, exist_ok=False)
(out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
(out / 'generation.json').write_text(json.dumps(extractor.last_generation, ensure_ascii=False, indent=2), encoding='utf-8')
print(out)
PY
```

위 예제는 저장 성공 시 경로를 출력한다. 모델 검증 실패는 예외로 종료되며 이를 정상 결과로 바꾸지 않는다.
실패 raw까지 체계적으로 저장하려면 아래 평가 runner를 사용하거나 Runtime의 실패 로깅을 연결한다.

### 8개 사례로 두 모델 평가

호스트에서 `docker exec -it jhbak_ct bash`로 들어간 뒤 실행한다.

```bash
cd /jhbak/CHAIN_agent_v0.3
export PYTHONDONTWRITEBYTECODE=1
PY=/data/data2/jhbak/CHAIN_agent_summary_prototype/runtime/gemma4-venv/bin/python
RUN=/data/data2/jhbak/CHAIN_agent_summary_prototype/outputs/s1_fresh_run

# 매번 새로운 RUN 경로: 입력·GT·프롬프트·환경 manifest 준비
$PY -m chain_agents.summary.history_s1_experiment --root "$RUN" --prepare
# Qwen GPU 2 / Gemma GPU 3 병렬; 각 모델이 두 생성 순서 실행
$PY -m chain_agents.summary.history_s1_experiment --root "$RUN"
# 저장 결과 평가와 독립 HTML 생성
$PY -m chain_agents.summary.history_s1_report "$RUN"
```

한 모델·한 순서만 실행하려면 준비 이후 아래 명령을 사용한다.

```bash
$PY -m chain_agents.summary.history_s1_experiment --root "$RUN" \
  --model gemma4_12b_it --gpu 3 --method direct
```

미실행 조건은 보고서에서 따로 표시한다. 기존 결과가 있는 같은 조건에 덮어쓰지 않는다.
`direct`는 `question/status/value/evidence`, 비교용 `evidence_first`는 `question/evidence/status/value` 순서다.
모두 문서 전체에 한 번 호출한다. Qwen thinking은 끄고 두 모델 모두 greedy / 8192 출력 토큰이다.
loader의 옛 1800 기본값은 S1 경로에서 8192로 명시적으로 대체된다.

확정 실행: `/data/data2/jhbak/CHAIN_agent_summary_prototype/outputs/summary_s1_gt_review_parallel_20261008_v2`.
`comparison.html`은 서버 없이 파일로 열 수 있다. 모델 가중치·캐시·로그·결과는 data2/data3에 둔다.
사용 환경은 Transformers 5.19 / torch 2.8+cu126이며 정확한 버전·모델 revision은 해당 `manifest.json`과 모델별 JSON에 기록된다.

| 8개 합성 사례 / 48개 항목 | direct | evidence_first |
|---|---:|---:|
| Qwen3.5-9B | 40/48 | 35/48 |
| Gemma4-12B-it | 48/48 | 42/48 |

한 fact가 유효하지 않으면 사례 전체가 반환되지 않아 그 사례 6개가 0점이다.
이전 실행과의 비교에는 GT/공통 규칙 변경이 섞이므로 현재 두 arm 내부에서 생성 순서 효과를 비교한다.

## 남은 연동 과제

`api_adapter.mock_output`이 items object, 실행 ID/시각, confirmation_status를 추가한다.
confidence는 null, 항혈소판제 값은 boolean, 미확인/상충/근사시간은 확장 상태로 보존한다.
`typed_items`에 내부 결과를 손실 없이 함께 제공한다. 원안 P-07과 확장 프로필의 수락 규칙은 JLK/WG4 합의가 필요하다.
전체 차이는 [API 가이드](API_INTEGRATION.md)와 [원안 대조표](MOCK_V012_ALIGNMENT.md)에 적었다.
API 구현에서도 확정한 모델 프롬프트·GT·추출 규칙은 변경하지 않았다. 분리 질문 ID의 resolver 허용 목록만 일치시켰다.
