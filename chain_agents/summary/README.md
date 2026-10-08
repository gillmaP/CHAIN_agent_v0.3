# Clinical Summary Agent

Summary S1은 workflow의 S1 진입 시 지정된 자료를 읽고, 요청된 임상 질문에 대한 facts와 근거를 반환합니다.

## 처리 흐름

1. 요청에서 episode, encounter, 자료 참조, 질문을 확인합니다.
2. data_api로 활성 약물, 문제 목록, 최근 내원 기록, 문서 원문을 조회합니다.
3. 코드가 구조화 자료를 처리하고 extractor가 문서 원문에서 사실과 인용을 추출합니다.
4. 코드가 출처·상태·출력을 검증하고 결과를 반환합니다.

## 실행

Python 3.11 이상, 저장소 루트에서 실행합니다.

    python -m examples.summary_s1

이 예제는 합성 자료와 고정 extractor를 사용합니다. 모델 추론 예제는 사전 설치한 선택 의존성을 사용합니다.

    python -m pip install -r chain_agents/summary/requirements-llm.txt
    python -m examples.summary_s1 --model qwen35_9b --gpu 2 --model-dir /path/to/Qwen3.5-9B

모델 키, 장치 번호, 가중치 경로는 실행 환경에 맞게 지정합니다.

## Orchestrator 호출

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

data_api와 extractor는 Host에서 준비해 주입합니다. data_api는 get(path) -> dict, extractor는 extract(documents, questions) -> dict를 제공합니다. input_observer는 선택 서비스입니다.

## 입출력

요청에는 episode_id, encounter_id, trigger, input_references, questions가 포함됩니다. workflow trigger는 S1 진입을 나타냅니다. 자료 참조는 실제 조회 가능한 버전으로 지정합니다.

결과는 summary-s1-fields/v1 형식이며 items와 missing_information을 포함합니다. 각 item은 다음 구조를 사용합니다.

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

status, question별 value, 대안 값과 인용 규칙은 [CONTRACT.md](CONTRACT.md)에 정리했습니다.

## 자료 조회와 모델

Summary는 data_api.get(path) 인터페이스를 사용합니다. 개발용 endpoint 예제와 자료 검증 규칙은 data_contract.py와 site_data_api.py에 있습니다. Host는 같은 인터페이스를 제공하는 client를 주입합니다.

문서 원문은 extractor로 전달됩니다. LLM prompt와 로컬 모델 로딩은 extractor.py와 local_model.py에 있습니다. 모델 실행 시 선택한 모델의 requirements를 설치하고, 가중치 경로를 실행 환경에 맞게 지정합니다.

## context 호환 mode

같은 모듈에는 v0.3 starter에서 이어진 context mode도 있습니다. 이미 만들어진 scoped snapshot facts를 읽어 structured_context, missing_information, cache를 반환합니다. 이는 S1과 별도의 요청 경로이며 S1 workflow 안에서 추가로 호출되는 단계가 아닙니다. 현재 프로젝트 Summary의 주 경로는 S1입니다.

## 주요 파일

| 파일 | 역할 |
|---|---|
| agent.py | 공통 invoke 진입점과 mode 분기 |
| summary.py | S1 자료 처리와 근거 결합 |
| contract.py | S1 요청·결과 검증 |
| data_contract.py | 자료 종류와 조회 요청 정의 |
| site_data_api.py | HTTP client 예제 |
| extractor.py, local_model.py | 문서 추출과 로컬 모델 실행 |

테스트는 저장소 루트에서 실행합니다.

    python -m unittest discover -s tests -v
