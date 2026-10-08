# 1: Stroke Screening Agent (CHAIN Mock v0.12)

## 1. 모델과 실행

- `qwen35_9b` → `Qwen/Qwen3.5-9B`
- `gemma4_12b_it` → `google/gemma-4-12B-it`
- `medgemma15_4b_it` → `google/medgemma-1.5-4b-it`
- 모델은 `prototype.py`에 명시된 revision manifest와 일치해야 합니다.

저장소 루트(`CHAIN_agent_v0.3/`)에서 실행합니다. 모델 가중치 경로는 **프로그램의 기본값이 아니며** 설치된 모델을 명시해야 합니다.

```bash
python -m pip install -r chain_agents/screening/requirements-llm.txt
python -m unittest discover -s tests -v
python scripts/screening_experiment.py smoke  # 고정 합성 응답, LLM 아님

python scripts/screening_experiment.py run --model qwen35_9b --gpu 0 \
  --model-root /path/to/models --output ./results/qwen35_9b_result.json

# 공식 Mock v0.12 I/O 어댑터: 직접 함수 호출을 시험하는 합성 테스트
python scripts/screening_v012_demo.py --mode smoke

# v0.12 Mock 요청 + 실제 모델 추론 (GPU/가중치 필요, 추가 출력 파일 없음)
python scripts/screening_v012_demo.py --mode gpu --model qwen35_9b --gpu 0 \
  --model-root /path/to/models --max-new-tokens 1800
```

## 2. v0.12 Orchestrator 입력 (정확히 7개 최상위 필드)

```text
episode_id: string
encounter_id: string
patient_id: string
trigger_event_id: string
input_references: string[]   # document:ID@version + encounter/observation/condition 참조
documents: [{document_id:string, version:int, document_type:string, text_hash:"sha256:<hex>"}]
structured_context: object   # age, sex, arrival_time, arrival_mode, triage_level,
                             # vital_signs, poct_glucose_mg_dl, problem_list,
                             # seizure_history, preexisting_hemiparesis
```

**전체 실제 예시:** `input_reference_only: true`에 따라 Agent가 Site Data API에서 원문을 조회합니다. 허용되는 문서 타입은 `ED_INITIAL_NOTE`, `ED_TRIAGE_NOTE`, 문서 ID·버전·환자·내원·SHA256을 일치 검증합니다. 문서 이외에 허용하는 참조는 `encounter:<encounter_id>`, `observation:vital_signs`, `observation:poct_glucose`, `condition:problem_list`뿐입니다. 다른 환자·미인가 참조·문서 변조는 오류로 거부합니다.

`structured_context`는 **Orchestrator/Runtime이 트리거 당시 승인된 스냅샷으로 전달**합니다. 본 Agent는 이후 시점의 관측치로 덮어쓰지 않습니다. 이 입력의 누락 가능 필드는 기본적으로 추론해 채우지 않으며, Runtime이 사실의 시각·접근권한을 보증해야 합니다.

## 3. Orchestrator 호출 및 결과 전달 위치

**진입점:** `chain_agents.screening.agent.invoke_v012(...)` (실제 로직: `v012_contract.py`).

```python
from chain_agents.screening.agent import invoke_v012
from chain_agents.screening.local_model import LocalScreeningModel
from chain_agents.screening.site_data_api import HttpSiteDataAPI

# 예
model = LocalScreeningModel('qwen35_9b', gpu='0')   # 모델은 프로세스당 재사용 권장
data_api = HttpSiteDataAPI(
    'https://trusted-site-node/chain/api/v0.1',
    bearer_token=authorized_execution_token, 
)
output = invoke_v012(
    official_screening_input,                   # 7-key dict
    execution_id=execution_id_from_runtime,    # Orchestrator 소유 ID
    data_api=data_api,                         # 승인된 read-only Tool 클라이언트
    model=model,
)
# output은 JSON 직렬화 가능한 Python dict — .json 파일을 수동으로 읽을 필요 없음
```

### Tool / Site Data API

`site_data_api.HttpSiteDataAPI`는 **클라이언트**이며 서버가 아닙니다. URL·인가 토큰으로만 `GET /documents/{id}?version={v}`, `GET /encounters/{id}`를 호출합니다. HTTPS만 허용하며 명시적으로 켠 localhost Mock만 HTTP를 허용합니다. 리다이렉트는 허용하지 않습니다. `SyntheticFixtureDataAPI`는 `examples/v012_screening_site_data_fixture.json`에서 3개의 합성 응답을 읽으며 병원 API 연결로 간주하지 않습니다. 구조화 문맥의 나머지 참조는 `structured_context`를 사용합니다.

## 4. v0.12 결과 형식 (정확히 16개 최상위 필드)

| 필드 | 형식/설명 |
|---|---|
| `agent_id`, `agent_version` | `stroke-screening-agent`, `0.3.0` |
| `execution_id`, `episode_id`, `encounter_id` | 실행 ID 및 입력에 연동된 식별자 |
| `result` | `{screening_result, proposed_state, clinical_label, priority}` |
| `confidence` | 0..1 **임시 근거 충족도 점수; 확률·임상 신뢰도로 해석 금지** |
| `rule_trace` | `[{rule, satisfied, basis}]` |
| `text_derived_findings` | `[{finding, label, snomed, source_ref, quote}]` |
| `clinical_times` | `{last_known_well, symptom_discovery, ems_arrival, source_ref, confirmation_status}` |
| `missing_information` | 문자열 배열 |
| `evidence` | `[{source_ref, quote, finding}]` |
| `produced_time` | ISO8601 `+09:00` |
| `processing_time_ms` | 음이 아닌 정수 |
| `model_info` | `rule_set`, `nlp_model`, `llm_tier` 등; 실제 모델/프롬프트/점수 정의 포함 |
| `disclaimer` | 의사결정 보조·HITL 경고 문구 |

**공식 Mock 원본 출력:** `examples/v012_screening_reference_output.json`. **실제로 생성한 합성 결과:** `python scripts/screening_v012_demo.py --mode smoke`의 stdout. 이 둘은 동일 환자라도 `confidence`, 원문 인용 수, `model_info` 등 내용이 **같을 필요가 없습니다**. 스키마 예시는 구조 검증 기준입니다. 모델 출력을 가공한 16-key 결과는 함수 반환 `dict`이며, 필요 시 `result_ref`와 `output_hash`를 생성/저장합니다.

LLM 내부 원시 출력 `{ "findings": [{code,status,source_ref,quote}] }`은 `validate_response`에서 출처/인용을 검사한 후 위 형태로 변환합니다. `REVIEW_REQUIRED`, 불완전한 JSON, 근거 없는 양성, 참조 오류는 **예외로 거부**하며 `NEGATIVE`로 임의 변환하지 않습니다. 상태 S0→S1 전이는 `result.screening_result == POSITIVE`, 정상 종료, 근거 1건 이상, 중복 아님, 초기 S0 등 **guard에서만** 수행합니다.

### 임상 및 계약 주의

- `confidence`는 v0.12 샘플의 숫자 형식을 맞춘 **미보정 규칙 기반 coverage score**입니다. `0.93`을 복제하지 않으며, 어떤 임상 확률도 의미하지 않습니다.
- R3는 v0.12 예시의 `R3_NO_STRONG_ALTERNATIVE` 형태를 출력하지만, 프로토타입은 제공된 근거 내 대체 원인만 확인합니다. 확인하지 않은 원인을 배제한 것으로 취급하지 않습니다. Screening 규칙은 임상 승인된 알고리즘이 아닙니다.
- 임상 시각은 명시적인 원문 인용에서만 추출합니다. 발견 시각과 LKW를 구분하며 찾지 못한 값은 `null`입니다. 자동 문맥 확정이 아니라 `UNCONFIRMED_NLP_EXTRACTED`입니다.

## 5. 검증 방법과 제한

```bash
python -m unittest discover -s tests -v
python scripts/screening_v012_demo.py --mode smoke
```

테스트는 입력 7개/출력 16개 키, 하위 필드, 원문 해시, 환자/내원 불일치, 범위 초과, 원문 인용 위조, 잘못된 LLM JSON, 합성 결과 반환을 포함합니다.
