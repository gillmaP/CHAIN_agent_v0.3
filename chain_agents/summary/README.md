# Clinical Summary Agent

Summary Agent는 업무 흐름의 S1 단계에서 질문에 답할 자료를 모으고 정리합니다. 표처럼 구조화된 자료는 코드가 읽고, 진료기록 문서는 내부 LLM이 사실과 원문 인용을 찾습니다. 코드가 질문별 결과를 확인해 반환합니다.

## 처리 순서

1. 환자·내원 정보, 읽을 자료 목록, 질문을 확인합니다.
2. 자료 조회 기능(`data_api`)으로 약물, 문제 목록, 최근 내원 정보와 문서를 가져옵니다.
3. 구조화 자료는 코드가 처리하고 문서 원문은 추출기(`extractor`)가 분석합니다.
4. 질문별 답과 근거를 확인해 결과를 반환합니다.

## 가상 자료로 먼저 실행하기

Python 3.11 이상, 저장소 루트에서 실행합니다.

```bash
python -m examples.summary_s1
```

이 예제는 가상 자료와 고정된 추출 결과를 씁니다. 입출력 모양을 보여주며 LLM은 실행하지 않습니다.

## 실제 로컬 LLM으로 실행하기

모델 가중치가 저장된 경로와 사용할 GPU 번호를 지정합니다.

```bash
python -m examples.summary_s1 --model qwen35_9b --gpu 2 --model-dir /path/to/models/Qwen3.5-9B
python -m examples.summary_s1 --model gemma4_12b_it --gpu 3 --model-dir /path/to/models/gemma-4-12B-it
```

`/path/to/...`를 실제 모델 경로로 바꿉니다. 실행 환경에는 PyTorch와 Transformers가 설치되어 있어야 합니다. 선택 설치 항목은 다음 파일에 있습니다.

```bash
python -m pip install -r chain_agents/summary/requirements-llm.txt
```

각 명령은 가상 S1 자료를 지정한 모델에 넣고 JSON 결과를 터미널에 출력합니다.

## Orchestrator에서 호출하는 위치

Summary의 Python 진입점은 `chain_agents.summary.agent.invoke`입니다. Orchestrator 쪽 실행 환경에서 요청을 만들고 자료 조회·문서 추출 기능을 준비해 전달합니다.

```python
from chain_agents.summary.agent import invoke
from chain_agents.services import AgentServices

request = {
    "mode": "s1",
    "patient_id": "PAT-example",
    "encounter_id": "ENC-example",
    "episode_id": "EP-example",
    "trigger": {"state_enter": "S1"},
    "input_references": ["document:NOTE-example@1"],
    "questions": ["anticoagulant_use", "previous_stroke", "lkw_records"],
}
services = AgentServices(data_api=data_api, extractor=extractor)
result = invoke(request, None, services)
```

- `request`: 환자·내원 정보, 읽을 자료, 답을 원하는 질문
- `data_api`: 요청에 적힌 자료를 가져오는 기능
- `extractor`: 문서 원문에서 질문별 사실과 인용을 찾는 기능
- `result`: Summary가 확인한 질문별 답과 근거

Agent 진입점은 Python 함수입니다. 실행 환경이 자료 조회와 모델 실행 기능을 준비해 Summary에 전달합니다.

## 입력 예시

```json
{
  "mode": "s1",
  "patient_id": "PAT-example",
  "encounter_id": "ENC-example",
  "episode_id": "EP-example",
  "trigger": {"state_enter": "S1"},
  "input_references": ["document:NOTE-example@1"],
  "questions": ["anticoagulant_use"]
}
```

## 결과 형식

요청한 질문마다 `items`에 하나의 결과가 들어갑니다. 질문 유형에 따라 `value`는 참·거짓, 문자열, 시간 정보처럼 달라질 수 있습니다.

```json
{
  "items": [
    {
      "question": "anticoagulant_use",
      "status": "documented",
      "value": true,
      "evidence": [
        {
          "source_ref": "document:NOTE-example@1",
          "quote": "현재 항응고제 apixaban 5 mg bid를 복용 중이다"
        }
      ],
      "alternatives": []
    }
  ],
  "missing_information": []
}
```

| 항목 | 뜻 |
|---|---|
| `question` | 답을 만들 질문 이름 |
| `status` | 자료에서 확인된 상태: `documented`, `not_stated`, `explicitly_unknown`, `conflicting`, `not_applicable` |
| `value` | 질문에 대한 값. 상태에 따라 값이 없을 수 있고 질문 종류에 따라 자료형도 다릅니다. |
| `evidence` | 값의 근거가 되는 원문 인용과 자료 위치 |
| `alternatives` | 서로 다른 값이 함께 발견될 때 비교할 후보 |
| `missing_information` | 답을 만들거나 확인하는 데 추가 자료가 필요한 내용 |

질문별 값 규칙은 [Summary 출력 형식](CONTRACT.md)에 있습니다.

## 코드 위치

- 입력 자료의 형식과 가상 조회기: `data_contract.py`
- 조회 기능을 연결하는 코드: `site_data_api.py`
- 문서 추출기: `extractor.py`
- 로컬 모델 실행: `local_model.py`
- Summary 요청 처리: `agent.py`

## context 방식은 무엇인가요?

`context`는 처음 Orchestrator 예제에 있던 기존 방식입니다. 이미 묶여 전달된 구조화 자료를 정리해 `structured_context`를 돌려줍니다.

S1은 자료 목록과 질문을 받고 필요한 문서와 자료를 조회해 질문별 답을 만듭니다. 둘은 입력과 결과가 다른 별개의 호출 방식입니다. 현재 중심은 S1이고 context는 기존 예제를 위해 남아 있습니다.

## 실행 확인

2026-10-08 실제 로컬 GPU에서 확인했습니다.

- Qwen3.5-9B, GPU 2: 예제 질문 6개를 반환하고 필수 출력 검사를 통과했습니다.
- Gemma4-12B-it, GPU 3: 같은 질문 6개를 반환하고 필수 출력 검사를 통과했습니다.
- 두 결과 모두 `missing_information`은 비어 있었습니다.

이는 가상 예제 한 건을 실제 모델로 실행한 확인입니다. 전체 테스트 명령은 저장소 루트에서 실행합니다.

```bash
python -m unittest discover -s tests -v
```
