# CHAIN Clinical Support Agents

이 저장소는 세 개의 독립된 임상 지원 Agent를 제공합니다. Orchestrator가 필요한 Agent를 골라 호출하고, 각 Agent는 맡은 결과만 반환합니다. Agent끼리 서로를 호출하거나 하나의 고정 임상 흐름을 실행하지 않습니다.

```text
Orchestrator / Host
  ├─ Stroke Screening Agent
  ├─ Clinical Summary Agent
  └─ tPA Decision Support Agent
```

## 각 Agent의 역할

| Agent | 하는 일 | 결과 |
|---|---|---|
| **Stroke Screening** | 진료 기록과 선별 정보를 살펴 뇌졸중 의심 근거를 찾음 | 선별 결과와 인용 근거 |
| **Clinical Summary** | 지정된 환자 자료에서 요청한 임상 정보를 질문별로 모음 | 상태·값·출처·인용, 미확인 정보 |
| **tPA Decision Support** | 구조화된 정보를 규칙에 대입해 검토 항목을 정리 | 규칙별 결과와 의료진 확인 항목 |

Screening과 Summary는 내부 LLM을 사용할 수 있습니다. tPA는 결정론적 규칙만 적용합니다. 세 Agent 모두 의료진의 판단을 대신하지 않습니다.

## 공통 호출 방식

각 모듈은 같은 Python 진입점을 사용합니다.

```python
invoke(request, snapshot, services) -> dict
```

공통점은 호출 방식뿐입니다. Agent마다 업무 입력과 결과는 다릅니다. Orchestrator의 등록 정보나 API 경로가 Agent를 고릅니다. 요청 본문에는 `agent`를 반복하지 않습니다. 한 가지 작업만 하는 Summary에는 `action`도 필요하지 않습니다. tPA의 `mode`는 `interim`과 `final` 중 평가 단계를 정하므로 유지합니다.

Summary는 한 번 호출해 요청한 모든 질문의 결과를 만듭니다. Orchestrator/Host가 결과를 저장하면 화면은 나중에 저장된 결과를 조회합니다.

## 실행

저장소 루트에서 Python 3.11 이상으로 실행합니다.

```bash
# Agent별 합성 입력 예제
python -m examples.run screening
python -m examples.run summary
python -m examples.run tpa

# 각 Agent 예제를 이어서 확인 (임상 workflow 실행은 아님)
python -m examples.run all

# 전체 테스트
python -m unittest discover -s tests -v
```

합성 예제는 입력과 출력 연결을 확인합니다. 실제 임상 기록에 대한 성능을 뜻하지 않습니다.

## 로컬 LLM 실행 예제

모델을 내려받고 의존성을 설치한 뒤, 로컬 가중치 디렉터리를 지정합니다. 외부 추론 API를 호출하지 않습니다.

```bash
# Summary
python -m examples.summary --model qwen35_9b --gpu 2 --model-dir /path/to/Qwen3.5-9B
python -m examples.summary --model gemma4_12b_it --gpu 3 --model-dir /path/to/gemma-4-12B-it

# Screening
python scripts/screening_model_demo.py --model qwen35_9b --gpu 2 --model-root /path/to/models
```

필요한 패키지는 [Summary 실행 안내](chain_agents/summary/README.md)와 [Screening 안내](chain_agents/screening/README.md)에 있습니다. tPA는 별도 모델 없이 실행됩니다.

## Summary 요청과 반환 예시

요청 본문은 환자·내원 식별자, 읽을 자료, 필요한 질문만 담습니다.

```json
{
  "patient_id": "PAT-example",
  "encounter_id": "ENC-example",
  "episode_id": "EP-example",
  "input_references": ["document:NOTE-example@1"],
  "questions": ["anticoagulant_use", "previous_stroke"]
}
```

Agent는 각 질문에 대해 `documented`, `not_stated`, `explicitly_unknown`, `conflicting`, `not_applicable` 상태 중 하나와 타입에 맞는 값을 반환합니다. 원문 근거는 `evidence`에 보존합니다.

## Orchestrator와 Host가 맡는 부분

Python 함수가 Agent의 현재 연결점입니다. 이를 REST API로 노출하는 서버와 병원별 EMR/OCS 연결은 Host가 맡습니다.

| Host 작업 | 이유 |
|---|---|
| 등록 정보 또는 API 경로로 Agent 선택 | Agent 식별은 실행 라우팅이며 임상 입력이 아님 |
| Summary가 쓸 자료 조회 기능과 내부 모델 실행 환경 제공 | 병원별 데이터 권한과 모델 배포는 Agent 규칙과 별개 |
| Agent 결과 저장 및 화면 조회 지원 | 저장된 Summary를 다시 표시할 때 모델을 재호출하지 않음 |
| 실행 성공·실패와 재시도 관리 | 기술 실행 상태와 임상 결과 상태를 구분 |

연동 시 필요한 최소 입력·결과와 책임 경계는 [Orchestrator 연동 안내](docs/INTEGRATION.md)에, 공통 및 Agent별 필드는 [입출력 설명](docs/CONTRACT.md)에 정리했습니다.

## 폴더 안내

```text
chain_agents/screening/   선별 근거 추출과 규칙
chain_agents/summary/     질문별 임상정보와 근거 정리
chain_agents/tpa/         구조화 정보 검토 규칙과 계산
examples/                 합성 입력과 실행 예제
tests/                    계약과 규칙 확인
docs/                     연동·입출력·정리 기록
```
