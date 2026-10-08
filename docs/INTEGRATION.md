# Orchestrator에서 Agent를 부르는 방법

## 전체 흐름

Orchestrator는 업무 순서를 관리하는 별도 프로그램입니다. 필요한 시점에 Agent를 부르고, Agent의 결과를 받아 다음 단계로 넘깁니다.

각 Agent는 이 저장소 안의 Python 모듈입니다. 실행 환경이 요청, 입력 자료, 사용할 기능을 준비한 다음 Agent 함수를 호출합니다.

## Agent를 부르는 Python 함수

```python
invoke(request, snapshot, services) -> dict
```

| 이름 | 쉬운 설명 |
|---|---|
| `request` | 이번 작업에서 무엇을 할지 적은 요청 |
| `snapshot` | 호출 시점에 전달하는 구조화 자료 묶음. 사용하지 않는 경로에서는 `None`일 수 있습니다. |
| `services` | 자료 조회, 모델 실행 등 Agent가 사용할 기능 |
| 반환값 | Agent가 만든 Python 결과. Orchestrator 쪽에서 저장하거나 다음 단계에 전달합니다. |

## Summary의 두 가지 호출 방식

Summary에 두 경로가 있는 것은 서로 다른 입력 방식이 필요하기 때문입니다. 한 작업에서 둘 다 연달아 실행하지 않습니다.

| 경로 | Agent가 받는 것 | Agent가 돌려주는 것 | 주 용도 |
|---|---|---|---|
| S1 | 환자·내원 정보, 읽을 자료 목록, 질문 | 질문별 `items`, `missing_information` | 필요한 자료를 조회해 질문에 답함 |
| context | Orchestrator가 미리 정리한 snapshot 자료 | `structured_context`, `missing_information`, `cache` | 처음 예제에 있던 기존 요약 |

S1에서 쓰는 기능은 두 가지입니다.

- `data_api.get(path)`: 요청에 포함된 구조화 자료나 문서를 가져옵니다.
- `extractor.extract(documents, questions)`: 문서 원문에서 질문별 사실과 인용을 찾습니다.

실행 환경은 이 기능들을 `AgentServices`에 넣어 Summary 진입점에 전달합니다. 연결 코드는 `chain_agents/services.py`, `chain_agents/summary/agent.py`, `chain_agents/summary/site_data_api.py`, `chain_agents/summary/extractor.py`에 있습니다.

## Orchestrator 예제와 Summary S1

참조 Orchestrator 예제는 기존 context 호출을 보여줍니다. 이 저장소에는 질문별 요약을 처리하는 S1 호출도 구현되어 있습니다. S1을 Orchestrator 실행 흐름에 연결할 때 Orchestrator 쪽에서 S1 요청을 만들고, 실행 환경에서 `data_api`와 `extractor`를 준비해 Summary에 전달합니다.

가상 입력으로 실행하는 예제는 저장소 루트에서 확인할 수 있습니다.

```bash
python -m examples.run all
python -m examples.run_integrated
python -m examples.summary_s1
```

`examples.summary_s1`은 고정된 추출 결과를 씁니다. 실제 모델을 시험하려면 [Summary 실행 안내](../chain_agents/summary/README.md)의 GPU 명령을 실행합니다.

## v0.3과 v0.12 표기

- **v0.3**: 별도 Orchestrator 저장소의 Agent 요청과 호출 예제에 붙은 표기
- **Mock v0.12**: 공유받은 Mock PDF와 코드 자료 묶음에 붙은 표기

두 표기는 서로 다른 참고 자료의 버전입니다. 이 저장소의 Agent나 LLM 버전은 아닙니다. 세 Agent별 입력과 결과 예시는 [Agent별 입력과 결과](CONTRACT.md)에 있습니다.
