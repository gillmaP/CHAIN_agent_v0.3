# CHAIN Agent Prototype

뇌졸중 진료 지원 흐름에 필요한 세 가지 프로그램을 모은 프로토타입입니다. 각 프로그램은 맡은 일을 처리해 결과를 돌려주고, 별도 프로그램인 Orchestrator가 업무 순서에 맞춰 호출합니다.

## 어떤 프로그램이 있나요?

| 프로그램 | 하는 일 |
|---|---|
| Stroke Screening | 진료 기록에서 뇌졸중 선별에 필요한 근거를 찾습니다. |
| Clinical Summary | 질문에 답할 자료를 모으고, 문서에서 관련 사실과 원문 인용을 찾습니다. |
| tPA Decision Support | 전달받은 구조화 정보에 정해진 규칙을 적용해 검토 결과를 만듭니다. |

## Summary는 어떻게 동작하나요?

현재 중심으로 구현한 경로는 업무 흐름의 **S1 단계**에서 시작합니다. S1은 업무 흐름에서 사용하는 단계 이름입니다.

```text
환자·내원 정보 + 읽을 자료 목록 + 질문
                    ↓
        필요한 자료를 조회
                    ↓
 표 형식 자료는 코드가 읽고, 문서 원문은 LLM이 읽음
                    ↓
 질문별 답·근거 인용·추가 확인 항목을 반환
```

## 먼저 실행해 보기

Python 3.11 이상, 저장소 루트에서 실행합니다.

```bash
python -m examples.run all
python -m examples.run_integrated
python -m unittest discover -s tests -v
```

이 명령들은 저장소의 가상 자료로 세 Agent의 호출과 결과 형식을 확인합니다. 실제 LLM을 띄우지는 않습니다. 전체 테스트는 107개입니다.

Summary 입출력 모양을 보려면 다음을 실행합니다. 이것도 가상 자료와 고정된 추출 결과를 씁니다.

```bash
python -m examples.summary_s1
```

## GPU에서 실제 LLM 실행하기

로컬에 모델 가중치가 준비된 Python 환경과 NVIDIA GPU가 필요합니다. 저장소 루트에서 모델 경로와 GPU 번호를 지정합니다.

```bash
python -m examples.summary_s1 --model qwen35_9b --gpu 2 --model-dir /path/to/models/Qwen3.5-9B
python -m examples.summary_s1 --model gemma4_12b_it --gpu 3 --model-dir /path/to/models/gemma-4-12B-it
```

`/path/to/...`는 모델이 저장된 실제 경로로 바꿉니다. 명령은 가상 환자 자료를 넣고 지정한 모델로 Summary를 실행한 뒤 JSON 결과를 출력합니다. [Summary 실행 안내](chain_agents/summary/README.md)에서 자세히 볼 수 있습니다.

## Summary에 두 호출 방식이 있는 이유

Summary에는 입력과 결과가 다른 두 호출 방식이 있습니다. 하나의 Summary가 연달아 두 번 실행된다는 뜻은 아닙니다.

| 이름 | 들어오는 자료 | 돌려주는 결과 | 설명 |
|---|---|---|---|
| S1 | 환자·내원 정보, 자료 목록, 질문 | 질문별 답과 근거 | 필요한 자료를 찾아 질문에 답하는 현재 중심 경로 |
| context | 이미 묶어 전달한 구조화 자료 | `structured_context` | 처음 Orchestrator 예제에 있던 기존 방식 |

현재 작업의 중심은 S1입니다. context는 기존 호출 예제와 연결할 수 있도록 함께 남아 있습니다.

## v0.3과 v0.12는 무엇인가요?

두 숫자는 서로 다른 참고 자료에 붙은 표기입니다. 이 저장소의 Summary나 LLM 버전을 뜻하지 않습니다.

- **v0.3**은 별도 [Orchestrator 저장소](https://github.com/donggunseo/chain-orchestrator-v03)의 Agent 요청·호출 예제에 붙은 표기입니다.
- **Mock v0.12**는 공유받은 CHAIN Mock PDF와 코드 묶음의 버전 표기입니다. 업무 흐름과 예시 입력을 설명하는 자료입니다.

Screening에는 두 자료의 호출 예제가 모두 있고, Summary에는 S1 경로와 기존 context 경로가 있습니다.

## 처음 보는 용어

| 용어 | 쉬운 설명 |
|---|---|
| Orchestrator | 업무 순서를 관리하고 필요한 Agent를 부른 뒤 결과를 받는 프로그램 |
| Agent | 정해진 한 가지 일을 처리하는 프로그램 |
| snapshot | Agent를 한 번 부를 때 전달하는 구조화 자료 묶음 |
| request | 이번에 할 일과 답을 원하는 질문 |
| services | Agent가 자료를 조회하거나 모델을 실행할 때 사용하는 기능 |
| LLM | 문서처럼 자유롭게 작성된 글에서 필요한 사실을 찾는 언어 모델 |
| API | 프로그램끼리 요청과 결과를 주고받는 방법. 이 저장소의 Agent 진입점은 Python 함수입니다. |

## 더 자세히 보기

- [Summary 실행, 입력·출력, LLM 연결](chain_agents/summary/README.md)
- [Screening 실행 안내](chain_agents/screening/README.md)
- [tPA 실행 안내](chain_agents/tpa/README.md)
- [Orchestrator에서 Agent를 부르는 위치](docs/INTEGRATION.md)
- [Agent별 입력과 결과 예시](docs/CONTRACT.md)
