# Clinical Summary Agent

S1에서 요청받은 환자 자료를 조회하고, 약물·과거력·LKW 정보를 근거와 함께 반환하는 프로토타입입니다.
구조화 자료는 코드로 처리하고 문서 원문은 내부 LLM을 한 번 호출해 추출합니다.

```text
S1 요청 → 지정 자료 조회·검증 → 입력 저장 → 코드 + 내부 LLM
       → 출력 검증·근거 결합 → 결과 저장 → API 조회 / UI 표시
```

## 1. 빠른 시작

저장소 루트에서 실행합니다. **Python 3.11 이상**이면 GPU 없는 데모를 실행할 수 있습니다.
데모는 합성 자료와 고정 추출기를 사용하며 모델 성능을 평가하지 않습니다.

```bash
python -m chain_agents.summary.api_service \
  --demo --host 127.0.0.1 --port 8091 \
  --store-root /data/data2/chain-summary/demo
```

다른 터미널에서 예제 요청을 받아 실행합니다. 요청 파일도 data2/data3에 저장합니다.

```bash
curl -fsS http://127.0.0.1:8091/examples/s1 \
  | python -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["request"]))' \
  > /data/data2/chain-summary/demo/request.json

curl -i -X POST 'http://127.0.0.1:8091/agents/clinical-summary-agent/invoke?format=typed' \
  -H 'Content-Type: application/json' -H 'X-Execution-ID: EXE-demo-001' \
  --data-binary @/data/data2/chain-summary/demo/request.json

curl -fsS 'http://127.0.0.1:8091/agent-results/EXE-demo-001?format=typed'
```

`--store-root`는 쓰기 가능한 `/data/data2` 또는 `/data/data3` 아래여야 합니다.
운영 인증을 설정한 경우 모든 호출에 `Authorization: Bearer <token>`을 전달합니다.

## 2. 요청과 결과

요청은 환자·내원·episode 식별자, S1 진입 정보, 조회할 자료 참조, 고정 질문 ID로 구성합니다.
아래는 형식 설명용 합성 예시입니다. 바로 실행할 때는 `/examples/s1`의 본문을 사용하세요.

```json
{
  "patient_id": "PAT-example",
  "encounter_id": "ENC-example",
  "episode_id": "EP-example",
  "trigger": {"state_enter": "S1"},
  "input_references": [
    "medication:active",
    "condition:problem_list",
    "encounter_history:6m",
    "document:NOTE-example@1"
  ],
  "questions": [
    "anticoagulant_use",
    "recent_surgery_or_bleeding",
    "previous_stroke",
    "lkw_records"
  ]
}
```

`format=typed` 결과의 `items`에는 질문별로 다음 형태의 항목이 들어갑니다.

```json
{
  "question": "anticoagulant_use",
  "status": "documented",
  "value": false,
  "evidence": [
    {"source_ref": "document:NOTE-example@1", "quote": "현재 항응고제를 복용하지 않는다"}
  ],
  "alternatives": []
}
```

| 결과 형식 | 용도 |
|---|---|
| `format=typed` | `summary-s1-fields/v1`. 질문별 `items` 배열. 신규 연동 권장 |
| 기본값 `format=mock` | `clinical-summary-integration/v1`. Mock 형태의 `items` 객체와 원본 `typed_items` 배열 |

POST 성공 본문은 결과 자체입니다. GET 결과 조회는 `execution_id`, `status`, `output_hash`, `output` 등을 감싼 응답입니다.
`X-Execution-ID`와 실행 상태 URL은 응답 헤더에도 있습니다.
질문·상태·시간값·근거 및 기본 응답의 변환 규칙은 **[CONTRACT.md](CONTRACT.md)**를 참고하세요.

## 3. HTTP API

| Method / 경로 | 역할 |
|---|---|
| `GET /health` | 준비 상태 |
| `GET /openapi.json` | API 명세 |
| `POST /agents/clinical-summary-agent/invoke` | 실행. `async=true`로 비동기 요청 가능 |
| `GET /agent-executions/{execution_id}` | 실행 상태 및 입력 추적 정보 |
| `GET /agent-results/{execution_id}` | 저장 결과. `format=typed` 지원 |
| `GET /summary-results/latest?patient_id=...&encounter_id=...&episode_id=...` | 최근 실행과 최근 성공 결과. `format=typed` 지원 |
| `GET /examples/s1` | 실행 가능한 합성 요청. `--demo` 전용 |

`/chain/api/v0.1` 접두사도 지원합니다.

- 실행 상태: `QUEUED → RUNNING → SUCCESS / FAILED`.
- HTTP: `200` 완료, `202` 대기·진행 중, `400` 잘못된 요청, `401` 인증 실패, `404` 없음,
  `409` 실행 ID 충돌, `413` 본문 초과, `422` 입력 조회·검증 또는 추출 실패, `429` 대기열 초과, `504` 실행 시간 초과.
- 같은 `X-Execution-ID`와 본문은 저장된 실행을 재사용합니다. 같은 ID와 다른 본문은 409입니다.
  자료를 다시 조회하려면 새 실행 ID를 사용합니다.
- 최근 결과 API는 세 식별자가 일치하는 실행을 제출 순서로 선택합니다. 새 실행이 실패해도 이전 성공 결과를 보존하며
  `latest_execution`, `latest_success`, `has_newer_attempt`로 구분합니다. 성공 이력이 없으면 `latest_success:null`입니다.
- 최근 성공은 최신 병원 자료 반영을 보장하지 않습니다. 실행마다 질문 목록이 다를 수 있으므로 응답의 `questions`를 확인하세요.

## 4. 실제 모델 실행

모델 가중치를 로컬에 준비하고 `requirements-experiment.txt`의 고정 버전을 사용합니다.
새 환경에서는 data2/data3에 격리 환경을 만듭니다. 이미 준비된 서버 환경을 재설치할 필요는 없습니다.

```bash
python3.11 -m venv /data/data2/chain-summary/runtime
/data/data2/chain-summary/runtime/bin/pip install \
  torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 \
  --index-url https://download.pytorch.org/whl/cu126
/data/data2/chain-summary/runtime/bin/pip install -r chain_agents/summary/requirements-experiment.txt
```

`experiment.py:MODELS`에 정의된 모델 ID·revision·디렉터리 이름으로 가중치를 준비합니다.
서버는 `local_files_only`로 로딩하며 실행 중 모델을 다운로드하지 않습니다.

```bash
mkdir -p /data/data2/chain-summary/tmp
export HF_HOME=/data/data2/chain-summary/hf_cache
export TMPDIR=/data/data2/chain-summary/tmp
export PYTHONDONTWRITEBYTECODE=1

/data/data2/chain-summary/runtime/bin/python -m chain_agents.summary.api_service \
  --model gemma4_12b_it --gpu 3 --port 8091 \
  --model-root /data/data2/chain-summary/models \
  --data-api-url http://127.0.0.1:8080/chain/api/v0.1 --synthetic-data \
  --store-root /data/data2/chain-summary/gemma --timeout 120
```

위 명령은 합성 Data API 연결 예입니다. 실제 병원 연결에는 해당 HTTPS 주소를 사용하고 `--synthetic-data`를 제거합니다.
`--fixture-data <자료 JSON 경로>`로 HTTP 자료 조회를 대체할 수도 있습니다. 이 경우 실제 LLM을 실행하되 `mock_only:true`입니다.

| 모델 | `--model` | GPU | 두 모델을 함께 실행할 때 |
|---|---|---|---|
| Gemma4-12B-it | `gemma4_12b_it` | 3 | 포트 8091 / 별도 저장소 |
| Qwen3.5-9B | `qwen35_9b` | 2 | 포트 8092 / 별도 저장소 |

모델당 프로세스 하나, 프로세스당 추론 worker 하나입니다. 한 SQLite 저장소를 여러 서버 프로세스가 공유하지 않습니다.
현재 HTTP 기본 설정은 검증된 `method=direct`, 최대 출력 8,192토큰, 문서 전체에 LLM 한 번 호출입니다.
`evidence_first`는 평가 runner의 비교 옵션이며 두 단계 모델 호출을 사용하지 않습니다.

### 인증과 배포

- `SUMMARY_API_TOKEN`: Summary API 호출용 bearer token. 외부 주소 바인딩(`--host 0.0.0.0`) 시 필수.
- `SUMMARY_DATA_API_TOKEN`: Site Data API로 전달할 bearer token.
- `--cors-origin`: 허용할 브라우저 origin. 공유 service token은 브라우저에 배포하지 않고 backend에서 사용합니다.
- HTTPS, 사용자·환자별 권한, WG4 실행 JWT, Event Bus는 통합 플랫폼에서 연결합니다.
  현재 bearer token을 WG4 인가 구현으로 간주하지 않습니다.

## 5. Orchestrator / Tool 연결

| 접점 | 파일·함수 |
|---|---|
| Python 진입점 | `agent.invoke(request, snapshot, services)` |
| S1 처리 | `history_s1_summary.run_history` |
| 자료 경로·환자·문서 버전 검증 | `mock_contract.endpoint / resolve` |
| Site Data API client | `api_adapter.HTTPDataAPI.get(path)` |
| 모델·프롬프트 | `history_s1_extractor.LocalS1Extractor` |
| 질문·값·근거 검증과 결합 | `history_s1_contract.py` |
| HTTP·저장·조회 | `api_service.py` |
| 입력·실행 버전 추적 | `input_audit.py` |

Python 호출 시 `snapshot=None`, `services.summary_data_api`, `services.summary_extractor`를 제공합니다.
입력 영속화가 필요하면 `services.summary_input_observer(snapshot)`을 주입합니다. HTTP runner에는 이미 연결되어 있습니다.

| 입력 참조 | Site Data API 상대 경로 |
|---|---|
| `medication:active` | `/patients/{patient_id}/medications?status=active` |
| `condition:problem_list` | `/patients/{patient_id}/conditions` |
| `encounter_history:6m` | `/patients/{patient_id}/encounters?months=6` |
| `document:{id}@{version}` | `/documents/{id}?version={version}` |

**공유 orchestrator v0.3과의 경계:** 본 S1 기능은 Mock v0.12의 임상정보 추출 역할을 기반으로 합니다.
공유 v0.3의 `context` 모드는 원천 Fact와 같은 `structured_context`를 요구하므로 S1 결과를 그대로 반환할 수 없습니다.
`input_references` 없는 기존 snapshot 호출은 원본 보존·캐시 경로로 유지합니다.
S1 mode/Agent 등록, 결과 수락, UI·후속 Agent 연결은 통합팀과 별도 계약을 맞춰야 합니다.

## 6. 입력 기록과 실패 처리

요청한 자료는 모두 필수입니다. 자료 조회·환자/버전 검증·구조화 자료 검증에 실패하면
`INPUT_RESOLUTION_FAILED`로 종료하고 모델을 호출하지 않습니다. 조회 실패를 임상 `not_stated`로 바꾸지 않습니다.

HTTP runner는 추론 전에 실제 자료와 해시를 SQLite에 저장하고, 실행 상태의 `input_audit`에 출처·조회 시각·코드 해시·런타임 버전을 남깁니다.
원문 입력과 raw generation은 일반 상태 응답에서 제외합니다. `coverage:complete`는 요청 자료 확보만 의미하며 모든 임상정보 확보를 뜻하지 않습니다.
순차 조회이므로 병원 DB 전체의 원자적 snapshot이나 과거 시점 조회를 보장하지 않습니다.
모델 가중치 revision을 별도로 확인하지 못한 실행은 `model_artifact_revision:null`로 기록합니다.

실패 결과와 이전 성공 결과를 모두 보존합니다. 시간 초과 후 늦은 성공은 수락하지 않지만 GPU 작업을 강제 종료하지는 않습니다.
서비스 재시작 시 중단된 작업은 `FAILED / INTERRUPTED`로 기록하고 자동 재실행하지 않습니다.
실행 자료·모델·로그는 data2/data3에 두고 Git에 포함하지 않습니다.

## 7. 테스트

```bash
python -m unittest discover -s tests -v

# 실제 모델 API 검증: 현재 검증 서버의 data2/jhbak 모델·fixture 경로를 사용합니다.
python -m chain_agents.summary.api_smoke \
  --model gemma4_12b_it --root /data/data2/chain-summary/check-gemma
```

2026-10-08 기준 단위·HTTP 회귀 테스트 **53개 통과**.
입력 보존, 조회 실패 시 모델 미호출, 질문 확장, 최근 성공 결과, 저장·재조회·인증·시간 초과를 검사합니다.
실제 API 검증도 Qwen(GPU 2), Gemma(GPU 3) 각각 2건 성공했습니다. 원래 Mock 입력의 약물 확인을 통과했고, 추가 양성 사례는 두 모델 모두 6/6 항목이 일치했습니다. 입력 저장과 최근 결과 조회도 확인했습니다.
이 테스트는 합성 자료 기반이며 임상 성능 검증이나 공유 orchestrator와의 전체 통합 시험은 아닙니다.

세부 사례·모델 출력 비교는 평가 HTML에서 설명합니다. 과거 Markdown 설명·실험 기록은 공유 폴더에서 정리하고 서버 data2에 백업했습니다.
