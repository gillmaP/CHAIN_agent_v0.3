# Clinical Summary Agent

S1 진입 시 지정된 자료에서 약물·과거력·마지막 정상 확인 시각을 추출하고 근거와 함께 반환하는 Python 모듈입니다.
구조화 자료는 코드가 처리하고 문서 원문은 내부 LLM을 한 번 호출합니다.

```text
Runtime 요청 → 주입된 데이터 클라이언트로 조회·검증
            → 구조화 자료 처리 + LLM 문서 추출
            → 출력 검증·근거 결합 → 결과 dict 반환
```

## 1. 빠른 시작

Python 3.11 이상, 저장소 루트에서 실행합니다. 서버·GPU·추가 패키지가 필요 없는 합성 예제입니다.

```bash
python -m examples.summary_s1
```

입력은 [summary_s1_fixture.json](../../examples/summary_s1_fixture.json), 실행 코드는
[summary_s1.py](../../examples/summary_s1.py)입니다. 기본 추출기는 고정 합성 응답이며 LLM 성능 평가가 아닙니다.
결과는 stdout으로 출력하며 DB나 파일을 만들지 않습니다.

## 2. Orchestrator 호출

S1 요약도 공통 `invoke(request, snapshot, services)`로 호출합니다. `invoke_s1`은 편의를 위한 wrapper입니다.

```python
from chain_agents.summary.agent import invoke
from chain_agents.services import AgentServices

# Runtime이 요청, 읽기 전용 자료 클라이언트, 재사용할 추출기를 준비합니다.
request = {**request, "mode": "s1"}
services = AgentServices(data_api=data_api, extractor=extractor,
                          input_observer=save_input_audit)  # observer는 선택
result = invoke(request, None, services)
# result를 Runtime의 결과 저장·UI 조회 경로에 연결합니다.
```

| 주입 항목 | 인터페이스 |
|---|---|
| `data_api` | `get(path) -> dict`. 합성 자료는 `mock_only=True` 표시 |
| `extractor` | `extract(documents, questions) -> dict`. 문서가 있을 때 필수 |
| `input_observer` | 추론 전 입력·감사 정보와 조회 실패 시 확보 범위를 받는 선택 콜백 |

v0.3 context 요청은 공통 `invoke(request, snapshot, services) -> dict` 경로로 전달합니다.
S1 reference request는 `mode=s1`, `snapshot=None`으로 전달하고 `services.data_api`,
`services.extractor`, 선택적인 `services.input_observer`를 주입합니다. `invoke_s1` wrapper는 같은
공통 진입점을 사용합니다.

**v0.3 context 경로는 별도 mode입니다.** `input_references`가 없는 요청은 snapshot facts를 보존하고
`structured_context`, `missing_information`, `cache`를 반환합니다. 신규 S1의 `items`를
`structured_context`에 넣지 않습니다. S1 결과를 공유 orchestrator에 연결하려면 출력 계약을 합의해야 합니다.

## 3. 입출력

```json
{
  "patient_id": "PAT-example",
  "encounter_id": "ENC-example",
  "episode_id": "EP-example",
  "trigger": {"state_enter": "S1"},
  "input_references": ["document:NOTE-example@1"],
  "questions": ["anticoagulant_use", "recent_surgery_or_bleeding", "previous_stroke", "lkw_records"]
}
```

반환은 `summary-s1-fields/v1` dict입니다. 식별자, 처리 질문, `items`, `missing_information`,
`model_info`, `mock_only`를 포함합니다. 항목 예시는 다음과 같습니다.

```json
{
  "question": "anticoagulant_use",
  "status": "documented",
  "value": false,
  "evidence": [{"source_ref": "document:NOTE-example@1", "quote": "현재 항응고제를 복용하지 않는다"}],
  "alternatives": []
}
```

질문별 값, 다섯 상태, 시간 정밀도, 상충 표현은 [CONTRACT.md](CONTRACT.md)에 정의했습니다.
입력·자료·모델 출력 검증 실패는 예외로 전달하며 정상 결과로 위장하지 않습니다.

## 4. Tool / 데이터 API 연결

`site_data_api.HTTPDataAPI`는 **외부 API 호출 클라이언트**입니다. HTTP 서버나 EMR 커넥터가 아닙니다.
URL·토큰은 Runtime 설정으로 전달하며 LLM에 전달하지 않습니다.

```python
from chain_agents.summary.site_data_api import HTTPDataAPI

data_api = HTTPDataAPI(trusted_base_url, token=execution_token)
```

| 참조 | 현재 Mock 기준 조회 경로 |
|---|---|
| `document:ID@version` | `/documents/{ID}?version={version}` |
| `medication:active` | `/patients/{patient_id}/medications?status=active` |
| `condition:problem_list` | `/patients/{patient_id}/conditions` |
| `encounter_history:6m` | `/patients/{patient_id}/encounters?months=6` |

공통 Tool이 같은 `get(path)` 인터페이스를 제공하면 HTTP 클라이언트 없이 그대로 주입할 수 있습니다.
하이젠 실제 API 명세·권한·시점 계약은 확정 후 연결해야 합니다. 순차 조회는 원천 DB의 원자적 snapshot이나
과거 as-of 조회를 보장하지 않습니다. 환자·문서 버전·내원 정보 및 필수 자료를 검증합니다.

## 5. 내부 LLM 실행

사전 다운로드된 로컬 가중치만 읽습니다. 모델·GPU·경로는 실행자가 지정합니다.
GPU에 맞는 PyTorch를 먼저 설치하고 선택 의존성은 [requirements-llm.txt](requirements-llm.txt)를 사용합니다.

```bash
python -m pip install -r chain_agents/summary/requirements-llm.txt
python -m examples.summary_s1 --model qwen35_9b --gpu 2 \
  --model-dir /data/data2/chain-summary/models/Qwen3.5-9B
```

실제 배포 경로에 맞춰 `--model-dir`를 바꾸세요. Gemma는 `--model gemma4_12b_it --gpu 3`으로 선택합니다.
같은 프로세스에서 GPU를 바꾸지 말고 모델별 프로세스를 사용합니다. 기본은 `direct`, 최대 출력 8192 tokens,
한 번 호출입니다. `evidence_first`는 같은 한 번 호출의 키 생성 순서 옵션입니다.
기존 평가의 프롬프트와 추출·검증·결합 규칙은 유지했습니다.

## 6. 파일과 책임

| 파일 | 역할 |
|---|---|
| `agent.py`, `logic.py` | 공통 호출 및 S1/기존 context 경로 |
| `summary.py`, `contract.py` | 자료 처리·근거 결합·질문/출력 검증 |
| `extractor.py`, `local_model.py` | 문서 프롬프트·LLM 추론·오프라인 로딩 |
| `data_contract.py`, `site_data_api.py` | 조회 경로·자료 검증·외부 API 클라이언트 |
| `input_audit.py` | 호출자가 저장할 입력 감사 정보 구성 |

Runtime에서 실행 ID, 성공/실패 envelope, 재시도, 결과 저장·UI 조회, 상태 전이와 알림을 연결해야 합니다.
해당 책임 배분과 최종 저장 경로는 통합 팀과 확정해야 합니다.
독립 HTTP/SQLite 서비스와 대규모 실험·HTML 생성 도구는 통합 패키지에서 제외하고 별도 보관했습니다.
EMR/OCS 직접 연결과 notifier는 구현하지 않습니다.

기존 테스트는 `tests/test_summary.py`, S1 계약 테스트는 `tests/test_summary_s1.py`와 `tests/test_summary_module.py`에 있습니다.
테스트 명령은 `python -m unittest discover -s tests -v`입니다.
이 프로토타입과 합성 예제만으로 임상 성능이나 전체 Orchestrator 통합 완료를 주장하지 않습니다.
