# Clinical Summary Agent

Summary는 Orchestrator가 지정한 환자·내원 자료와 질문을 한 번 받아, 질문별 답과 근거를 포함한 완성된 요약 결과를 반환합니다. Orchestrator가 결과를 저장해 나중에 화면에 다시 보여줍니다.

## 처리 순서

1. 환자·내원 ID, 조회할 자료 참조, 질문을 확인합니다.
2. 실행 환경의 `data_api`를 통해 요청된 활성 약물, 문제 목록, 최근 내원 정보와 문서를 조회합니다.
3. 표 형태 자료는 코드가 분류하고, 문서 원문은 내부 LLM이 사실과 원문 인용을 추출합니다.
4. 코드가 질문별 값과 상태, 자료 출처, 인용을 검증하고 문서 간 충돌을 정리합니다.
5. 전체 결과를 Orchestrator에 반환합니다. 화면은 저장된 결과를 재사용합니다.

요청된 자료 중 하나라도 조회 또는 검증에 실패하면 부분 결과를 성공으로 반환하지 않습니다. 기록에 언급이 없는 경우는 `not_stated`로 표시하고, 조회 실패와 분리합니다.

## 실행

Python 3.11 이상, 저장소 루트에서 실행합니다.

```bash
# 합성 자료와 고정 결과로 입력·출력 확인
python -m examples.summary

# 실제 로컬 모델로 문서 추출
python -m examples.summary --model qwen35_9b --gpu 2 --model-dir /path/to/Qwen3.5-9B
python -m examples.summary --model gemma4_12b_it --gpu 3 --model-dir /path/to/gemma-4-12B-it
```

실제 모델 실행 전 대상 서버에 맞는 CUDA 지원 PyTorch를 준비합니다. 공통 LLM 의존성은 저장소 루트에서 한 번 설치합니다.

```bash
python -m pip install -r requirements-llm.txt
```

## Orchestrator 호출 위치

Python 진입점은 `chain_agents.summary.agent.invoke(request, snapshot, services)`입니다.
등록 정보가 Summary 모듈을 선택하므로 요청 본문에 `agent`나 `action`을 넣지 않습니다. Summary는 `questions`에 요청할 항목을 받고 한 번의 호출로 전체 결과를 반환합니다.

```python
from chain_agents.services import AgentServices
from chain_agents.summary.agent import invoke

request = {
    "patient_id": "PAT-example",
    "encounter_id": "ENC-example",
    "episode_id": "EP-example",
    "input_references": ["document:NOTE-example@1"],
    "questions": ["anticoagulant_use", "previous_stroke", "lkw_records"],
}
services = AgentServices(data_api=data_api, extractor=extractor)
result = invoke(request, snapshot=None, services=services)
```

`data_api.get(path)`는 Host가 제공한 자료 조회 기능이고, `extractor.extract(documents, questions)`는 내부 모델 실행 기능입니다. 이 저장소는 병원별 API 연결이나 HTTP 서버를 구현하지 않습니다.

## 결과

요청한 질문마다 `items`에 하나의 항목이 반환됩니다.

```json
{
  "schema_version": "summary-items/v1",
  "episode_id": "EP-example",
  "encounter_id": "ENC-example",
  "input_references": ["document:NOTE-example@1"],
  "questions": ["anticoagulant_use"],
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

각 필드와 상태값, Boolean·시간 값 규칙은 [출력 형식](CONTRACT.md)에 있습니다.

## 코드 위치

- 요청 자료 참조와 검증: `data_contract.py`
- 자료 조회, 추출, 근거 결합: `summary.py`, `logic.py`
- 질문별 값·상태·근거 검증: `contract.py`
- LLM 프롬프트와 로컬 추론: `extractor.py`, `local_model.py`
- Python 호출 진입점: `agent.py`
