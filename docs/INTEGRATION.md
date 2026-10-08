# Orchestrator와 세 Agent 연결

## 한눈에 보는 흐름

Orchestrator가 업무 단계를 관리하고 필요한 Agent를 호출합니다. Agent는 자기 작업 결과를 반환하고, Orchestrator가 이를 저장하거나 다음 단계에 전달합니다.

```text
Orchestrator
  ├─ 선별 단계 ──> Stroke Screening ──> screening result
  ├─ 요약 단계 ──> Clinical Summary ──> question answers and evidence
  └─ tPA 검토 ───> tPA Decision Support ──> assessment
          <──────── 결과를 받아 다음 업무 단계 관리
```

세 Agent의 입력과 결과는 각자의 작업에 맞게 다릅니다. 공통점은 Python 함수로 호출되고 결과를 Python dictionary로 돌려준다는 것입니다.

## 공통 Python 호출 모양

```python
invoke(request, snapshot, services) -> result
```

- `request`: Agent가 이번에 할 작업과 처리 범위를 받습니다.
- `snapshot`: 호출 시점에 확정된 구조화 자료를 받습니다. Agent나 실행 방식에 따라 쓰지 않을 수 있습니다.
- `services`: Agent가 필요한 자료 조회나 실행 기능을 받습니다.
- `result`: 해당 Agent의 결과입니다. 각 Agent마다 결과 안의 필드는 다릅니다.

이 저장소는 Agent 함수를 제공합니다. Orchestrator를 실행하는 Host가 요청을 만들고, 필요한 서비스 기능을 연결한 다음, Agent 결과를 저장·전달합니다.

## Agent마다 무엇이 다른가요?

| Agent | 요청에 들어오는 자료 | 내부에서 하는 일 | 호출 위치와 필요한 서비스 |
|---|---|---|---|
| Screening | 선별 요청과 기록·구조화 자료 | 기본 경로는 backend에서 입력을 가져옵니다. Mock v0.12 경로는 문서에서 근거를 찾고 rule로 결과를 구성합니다. | `chain_agents.screening.agent.invoke`; `services.backend`. Mock v0.12는 `invoke_v012`로 모델과 자료 조회 기능을 받습니다. |
| Summary | 기존 context는 snapshot; S1은 환자·내원 정보, 자료 참조, 질문 | 구조화 자료는 코드가 처리하고 S1 문서는 LLM이 사실과 인용을 추출합니다. | `chain_agents.summary.agent.invoke`; S1은 `data_api`와 `extractor`를 받습니다. |
| tPA Decision Support | `interim` 또는 `final` 요청과 구조화 facts | 고정 규칙으로 필수 자료, 수치, 상태를 확인합니다. LLM을 부르지 않습니다. | `chain_agents.tpa.agent.invoke`; 요청과 snapshot을 사용합니다. |

### Summary의 context와 S1

Summary 경로가 두 개 있는 이유는 입력 자료와 반환 내용이 다르기 때문입니다.

- **context**: Orchestrator가 미리 묶은 snapshot을 받아 `structured_context`를 반환합니다. 처음 Orchestrator 예제에 있던 방식입니다.
- **S1**: 환자·내원 ID, 자료 참조, 질문을 받고 필요한 정보를 조회해 질문별 `items`와 `missing_information`을 반환합니다.

두 경로는 하나의 요약 작업에서 연속 실행되는 단계가 아닙니다. S1에서 자료를 조회하는 세부 코드는 `chain_agents/summary/data_contract.py`, `site_data_api.py`, 문서 추출은 `extractor.py`, 로컬 모델 호출은 `local_model.py`에 있습니다.

## 서비스는 어디서 연결하나요?

실행 Host가 서비스를 만들고 Agent에 전달합니다.

| 서비스 이름 | 사용하는 Agent | 기능 |
|---|---|---|
| `backend` | Screening 기본 경로 | screening 입력을 선택해 제공합니다. |
| `data_api` | Summary S1, Screening Mock v0.12 | 요청한 환자·내원·문서 자료를 조회합니다. |
| `extractor` | Summary S1 | 문서와 질문을 받아 질문별 사실·인용을 반환합니다. |
| 없음 | tPA | 전달받은 snapshot 값만 사용합니다. |

Summary S1의 호출 예시는 다음과 같습니다.

```python
from chain_agents.summary.agent import invoke
from chain_agents.services import AgentServices

services = AgentServices(data_api=data_api, extractor=extractor)
result = invoke(s1_request, None, services)
```

Orchestrator 쪽 연결은 S1 요청을 만들고 실행 환경에서 `data_api`와 `extractor`를 준비해 이 진입점에 전달하는 위치입니다. 세부 파일과 입출력 예시는 [각 Agent 입력과 결과](CONTRACT.md)를 참고하세요.

## 실행 예제는 무엇을 확인하나요?

저장소 루트에서 실행합니다.

```bash
python -m examples.run all
python -m examples.run_integrated
python -m unittest discover -s tests -v
```

- `examples.run all`은 기존 호출 예제에서 Screening, Summary context, tPA interim/final을 실행합니다.
- `examples.run_integrated`는 Screening, Summary S1, tPA interim/final의 합성 결과를 한 JSON에 모읍니다.
- 통합 예제 결과에 `pipeline_mapping: false`가 있는 것은 각 Agent 결과를 다음 Agent의 입력으로 연결하지 않는다는 뜻입니다.
- 전체 테스트는 세 Agent의 개별 동작과 입력·출력 검증을 확인합니다.

두 실행 예제는 합성 자료를 사용합니다. 실제 GPU 모델을 실행하는 명령은 [각 Agent README](../README.md#agent별-안내)에 있습니다.

## v0.3과 Mock v0.12

두 표기는 서로 다른 참고 자료의 버전입니다.

- **v0.3**은 별도 Orchestrator 코드의 요청·호출 예제에서 사용하는 표기입니다.
- **Mock v0.12**는 공유받은 CHAIN Mock PDF와 코드 자료의 버전입니다.

이 숫자는 이 통합 저장소나 LLM의 버전이 아닙니다. 저장소에는 두 자료의 입력 방식을 설명하는 Agent 예제가 함께 있습니다.
