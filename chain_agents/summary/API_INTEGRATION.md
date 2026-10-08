# JLK 통합: Summary HTTP / Tool API

구현: `api_service.py`(HTTP runner·SQLite), `api_adapter.py`(Site Data API client·응답 adapter).
public domain 함수 `agent.invoke(request, snapshot, services)`는 그대로다. 이 문서는 API 구현 이후의 현재 동작이다.

## 1. API 목록

| Method / path | 용도 | 성공 / 주요 오류 |
|---|---|---|
| `GET /health` | 모델 로딩 이후 준비 상태 | 200 |
| `GET /openapi.json` 또는 `/` | OpenAPI 3.0.3 명세·스키마 | 200 |
| `POST /agents/clinical-summary-agent/invoke` | S1 요청 본문 처리, 기본 동기 | 200 완료 / 202 대기 / 400 입력 / 422 추출 실패 / 504 timeout |
| 동일 경로 `?async=true` | 비동기 submit | 일반적으로 202; 이미 완료한 ID 재요청이면 200 |
| `GET /agent-executions/{execution_id}` | 상태와 제출/시작/완료시각 조회 | 200 / 404 |
| `GET /agent-results/{execution_id}` | 저장된 결과 envelope | 200 / 202 / 422 / 504 / 404 |
| invoke 또는 result에 `?format=typed` | 원래 S1 domain 형식 조회 | 같은 실행의 다른 표현; 재추론 없음 |
| `GET /examples/s1` | 실행 가능한 합성 요청 | `--demo`에서만 제공 |

`/chain/api/v0.1` prefix도 수락한다. 결과 저장 후 서비스 재시작해도 조회 가능하다.
`X-Execution-ID` header를 주면 같은 ID와 같은 본문은 같은 실행을 재사용한다. 같은 ID·다른 본문은 409다.
header가 없으면 `EXE-SUM-{uuid}`를 생성한다. 실행 ID별로 동작하며 episode 단위 최신 결과 자동 선택은 제공하지 않는다.
대기열 상한은 실행 중을 포함해 16개이며 초과하면 429다.

## 2. GPU 없는 UI 연결 예제

프로젝트 root에서 아래를 실행한다. Python 3.11+ 표준 라이브러리만으로 demo가 동작한다.
도메인 fixture를 처리하되 추출기는 합성 사례의 정답 후보를 사용한다. **모델 성능 테스트가 아니다.**
demo는 등록된 합성 문서와 정확히 같은 입력만 처리하고 모든 결과에 `mock_only:true`를 둔다.

```bash
python -m chain_agents.summary.api_service \
  --demo --host 127.0.0.1 --port 8091 \
  --store-root /data/data2/jhbak/CHAIN_agent_summary_prototype/api/demo \
  --cors-origin http://localhost:3000
```

다른 터미널에서:

```bash
BASE=http://127.0.0.1:8091
OUT=/data/data2/jhbak/CHAIN_agent_summary_prototype/api/client
mkdir -p "$OUT"
curl -fsS "$BASE/examples/s1" | python -c \
  'import json,sys; print(json.dumps(json.load(sys.stdin)["request"],ensure_ascii=False))' > "$OUT/request.json"

# 동기 호출. 같은 execution ID로 재시도하면 재추론 없이 같은 결과를 받는다.
curl -sS -D "$OUT/headers.txt" \
  -H 'Content-Type: application/json' -H 'X-Execution-ID: EXE-JLK-demo-001' \
  --data-binary @"$OUT/request.json" \
  "$BASE/agents/clinical-summary-agent/invoke" > "$OUT/output.json"

# 저장 결과 / 내부 typed 결과 조회
curl -sS "$BASE/agent-results/EXE-JLK-demo-001"
curl -sS "$BASE/agent-results/EXE-JLK-demo-001?format=typed"

# 비동기: 202와 Location header를 받고 status를 poll한다.
curl -i -H 'Content-Type: application/json' -H 'X-Execution-ID: EXE-JLK-demo-002' \
  --data-binary @"$OUT/request.json" "$BASE/agents/clinical-summary-agent/invoke?async=true"
curl -sS "$BASE/agent-executions/EXE-JLK-demo-002"
curl -sS "$BASE/agent-results/EXE-JLK-demo-002"
```

`QUEUED → RUNNING → SUCCESS/FAILED`. poll은 1–2초 간격을 권장한다. 아직 준비 중인 결과는 202다.
서버가 종료될 때 완료하지 못한 QUEUED/RUNNING 기록은 다음 시작 시 FAILED/INTERRUPTED로 바뀐다.
자동 재시도는 하지 않는다. 재실행 정책을 적용하려면 새 execution ID를 발급한다.

## 3. 실제 모델 + 병원/Mock Data API

서버 jhbak_ct에서 검증한 runtime을 사용한다. 로컬 model weights가 준비되어 있어야 한다.

새 Linux/Python 3.11 환경을 만들 경우 격리 venv에 설치한다. 기존 서버 runtime에는 재설치할 필요가 없다.

```bash
python3.11 -m venv /data/data2/chain-summary/runtime
/data/data2/chain-summary/runtime/bin/pip install \
  torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 \
  --index-url https://download.pytorch.org/whl/cu126
/data/data2/chain-summary/runtime/bin/pip install -r chain_agents/summary/requirements-experiment.txt
```

검증된 모델 repo/revision/directory는 `experiment.py:MODELS`에 고정돼 있다. 해당 revision의 weights를 로컬에 준비한다.
`--model-root /data/data2/chain-summary/models`로 다른 설치 경로도 지정할 수 있다. 그 아래 MODELS의 directory 이름을 사용한다.
HTTP 서버는 weights를 내려받지 않으며 local_files_only로 로딩한다. GPU 없는 demo에는 위 패키지 설치가 필요 없다.

```bash
cd /jhbak/CHAIN_agent_v0.3
export PYTHONDONTWRITEBYTECODE=1
export HF_HOME=/data/data2/jhbak/CHAIN_agent_summary_prototype/hf_cache
export TMPDIR=/data/data2/jhbak/CHAIN_agent_summary_prototype/runtime/tmp
PY=/data/data2/jhbak/CHAIN_agent_summary_prototype/runtime/gemma4-venv/bin/python

# SUMMARY_DATA_API_TOKEN은 배포 측 secret 환경변수로 주입한다. 코드/README에 토큰을 적지 않는다.
$PY -m chain_agents.summary.api_service \
  --model gemma4_12b_it --gpu 3 --port 8091 \
  --data-api-url http://127.0.0.1:8080/chain/api/v0.1 --synthetic-data \
  --store-root /data/data2/jhbak/CHAIN_agent_summary_prototype/api/gemma \
  --timeout 120
```

`--data-api-url`은 배포된 Site Data API 주소로 바꾼다. 위 mock 연결은 합성이므로 `--synthetic-data`를 사용한다.
실제 병원 자료 연결 때만 이 옵션을 제거한다. `localhost`는 현재 프로세스가 있는 컨테이너다.
다른 컨테이너의 API이면 해당 네트워크 DNS/주소를 설정해야 한다. 실제 병원 연결은 HTTPS를 사용한다.
외부 주소로 공개하려면 `--host 0.0.0.0`과 `SUMMARY_API_TOKEN`이 필요하다. UI/gateway가 `Authorization: Bearer ...`를 보낸다.
이 정적 서비스 token은 WG4의 실행별 JWT 검증을 대체하지 않는다. TLS와 사용자/환자별 권한 검증은 JLK gateway가 담당한다.
브라우저에 공유 service secret을 배포하지 말고 JLK backend를 통해 호출한다.

원래 Mock 자료 파일 + 실제 LLM 조합은 `--data-api-url` 대신 다음을 사용한다.

```bash
--fixture-data /data/data2/jhbak/CHAIN_agent_summary_prototype/datasets/mock_v012/15_data_api_simple.json
```

이 모드도 실제 LLM을 실행하지만 자료는 합성이므로 mock_only=true다.
HTTP 연결은 `--synthetic-data` 또는 응답의 `X-CHAIN-Mock:true`로 mock_only를 보존한다.
둘 다 없으면 실제 자료로 취급한다. 합성 HTTP API를 평가하는 smoke 모듈도 client를 명시적으로 mock_only=true로 만든다.

Qwen도 서비스하려면 **별도 프로세스**로 `--model qwen35_9b --gpu 2 --port 8092`와 별도 store-root를 사용한다.
모델당 한 worker로 순차 추론한다. 두 모델은 GPU2/GPU3에서 병렬로 동작한다.
한 SQLite store-root에 여러 서비스 프로세스를 동시에 연결하지 않는다. 시작 시 중단 작업 복구가 실행되기 때문이다.

## 4. 입력과 출력 계약

POST body는 PDF §8.3의 request 그대로다. `episode_id/encounter_id/patient_id/input_references/questions/trigger`가 필요하다.
HTTP runner는 `trigger.state_enter=S1`을 검사한다. 자유 자연어 question은 지원하지 않는다.
원래 수술/출혈 alias와 분리된 `recent_surgery`, `recent_bleeding` ID 모두 허용한다.
원문은 요청에 넣지 않고 Data API로 조회한다. `X-Execution-ID`는 본문 밖의 runtime metadata다.

기본 반환 프로필 `mock`은 다음 필드를 가진다.

```json
{
  "schema_version": "clinical-summary-integration/v1",
  "agent_id": "clinical-summary-agent",
  "agent_version": "0.3.0-prototype",
  "execution_id": "EXE-JLK-demo-001",
  "episode_id": "example-episode",
  "encounter_id": "example-encounter",
  "items": {
    "anticoagulant_use": {
      "status": "PRESENT", "value": true, "confidence": null,
      "sources": [{"source_ref": "document:example@1", "quote": "현재 항응고제를 복용한다"}],
      "confirmation_status": "UNCONFIRMED", "alternatives": []
    }
  },
  "missing_information": [],
  "produced_time": "2026-10-08T00:00:00+00:00",
  "processing_time_ms": 1000,
  "model_info": {},
  "mock_only": true,
  "typed_schema_version": "summary-s1-fields/v1",
  "typed_items": [{
    "question": "anticoagulant_use", "status": "documented", "value": true,
    "evidence": [{"source_ref": "document:example@1", "quote": "현재 항응고제를 복용한다"}],
    "alternatives": []
  }],
  "compatibility_notes": ["확장 계약의 차이는 실제 응답에 명시된다."]
}
```

위는 읽기 위한 단일 항목 합성 예시다. 실제 모든 항목/정의는 `/openapi.json`과 `/examples/s1` 응답을 사용한다.
`GET /agent-results/{id}`는 PDF와 같이 `{execution_id,agent_id,agent_version,status,output_hash,output}` envelope다.
output_hash는 **그 형식으로 반환하는 output**의 canonical JSON SHA256이다. typed와 mock 조회의 hash는 다를 수 있다.
POST 성공 본문은 envelope 없이 output 자체다. 실행 ID와 poll URL은 response header에도 있다.

### 원안과 남아 있는 명시적 차이

- 원래 schema 이름을 사칭하지 않고 `clinical-summary-integration/v1`로 구분한다. JLK/WG4 수락 규칙은 이 확장을 합의해야 한다.
- confidence는 항상 null이며 확인되지 않은 점수를 생성하지 않는다. confirmation_status는 모두 UNCONFIRMED다.
- 항혈소판제 value도 boolean이다. 약명·용량은 sources/typed_items에서 표시할 수 있지만 약명을 따로 추출하는 새 규칙은 넣지 않았다.
- 정확한 point LKW는 기존처럼 timestamp로 표시하고, approximate/interval 등의 시간 객체는 유지한다. 두 source가 있다고 의사 확인이나 CONSISTENT 상태로 승격하지 않는다.
- 수술/출혈 원래 alias 요청은 기본 items에서 결합한다. 어느 한쪽이 확실히 true면 true, 둘 다 명시적으로 false일 때만 false다. 나머지는 UNKNOWN/null로 표시하고 typed_items에 각 상태·상충을 그대로 둔다.
- 미기록은 NOT_STATED/null, 명시적 미확인은 UNKNOWN/null, 상충은 CONFLICTING/null/alternatives다. P-07의 “모든 항목에 근거”를 빈 항목에 억지로 채우지 않는다.
- `format=typed` 또는 `typed_items`를 사용하면 원래 S1 구조를 그대로 받아 정보 손실 없이 UI를 구성할 수 있다.

## 5. Tool/API 연결

`HTTPDataAPI.get(path)`에 reader가 구성한 다음 상대 경로가 들어간다.

| ref | GET path |
|---|---|
| medication:active | /patients/{id}/medications?status=active |
| condition:problem_list | /patients/{id}/conditions |
| encounter_history:6m | /patients/{id}/encounters?months=6 |
| document:{id}@{version} | /documents/{id}?version={version} |

client가 `SUMMARY_DATA_API_TOKEN`을 Authorization bearer로 전달한다. token은 LLM 입력이나 저장된 요청에 넣지 않는다.
HTTP timeout 기본 15초, 응답 상한 8MiB, redirect 차단이다. 자료 누락·네트워크·인증 실패는 실패 실행이며 정상적인 false로 처리하지 않는다.
demo 모드에만 위 GET 경로의 합성 응답을 제공한다. 이는 JLK가 화면/호출을 확인하기 위한 Tool API 예제다.
실제 Site Data API와 환자 DB를 Summary 서버가 대신 소유하거나 임의로 확장하지 않는다.

## 6. 저장·오류·운영 경계

- store-root의 SQLite에 request, 상태, 결과, hash, raw generation 및 실패 진단을 저장한다. data2/data3 밖 경로는 거부한다.
- 외부 실패 응답에는 환자 문서가 포함될 수 있는 raw/진단을 노출하지 않는다. 운영자가 로컬 DB에서 확인한다.
- status polling에는 raw/원문/결과 본문이 없다. 결과는 별도 GET으로 가져온다.
- 120초는 worker 실행 시작 기준이다. timeout이면 FAILED/504를 저장하고 늦게 끝난 결과를 SUCCESS로 바꾸지 않는다.
- **Python thread deadline은 GPU kernel을 강제 중단하지 않는다.** 해당 worker는 추론이 반환될 때까지 점유된다. 강제 취소·프로세스 재시작 감독은 배포 Runtime에서 구현해야 한다.
- 서버 시작 시 모델을 먼저 로딩하므로 /health 준비 상태는 로딩 이후다. startup 시간은 120초 추론 제한과 별개다.
- CORS는 지정한 한 origin에만 적용하며 wildcard가 아니다. authorization이 없으면 loopback에만 bind할 수 있다.
- Event Bus 발행, WG4 JWT 서명/일회성 검증, manifest 승인·scope, 운영 audit hash chain, 자동 재시도는 구현했다고 주장하지 않는다. 이 서버의 실행/결과 API를 JLK Runner에 연결하는 위치다.

## 7. 테스트와 재현

```bash
python -m unittest chain_agents.summary.test_api -v
python -m unittest discover -s tests -v

# 실제 LLM + loopback Tool API + 실제 HTTP + SQLite 저장/조회
$PY -m chain_agents.summary.api_smoke \
  --root /data/data2/jhbak/CHAIN_agent_summary_prototype/outputs/api_smoke_new_gemma \
  --model gemma4_12b_it
```

스모크 root는 새 경로여야 한다. 원안 Mock 요청과 positive-use 사례를 각각 1회 호출한다.
Qwen smoke는 GPU2, Gemma smoke는 GPU3로 배정한다. smoke의 HTTP 서버는 종료 시 닫힌다.
합성 자동 테스트는 API 구현을, 실모델 smoke는 네트워크·모델·출력검증까지의 연결을 확인한다. 임상 일반화 성능을 검증하는 테스트가 아니다.
