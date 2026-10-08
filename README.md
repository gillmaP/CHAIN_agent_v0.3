# CHAIN 임상 지원 Agent

본 저장소는 뇌졸중 진료 지원을 위한 세 개의 독립적인 Agent 프로토타입을 제공합니다. 각 Agent는 담당 업무를 수행하고 결과를 반환합니다. Agent 간 직접 호출이나 하나의 고정 임상 흐름은 구현하지 않았습니다.

## 목차

- [프로젝트 개요](#프로젝트-개요)
- [Agent별 역할](#agent별-역할)
- [호출 방식과 통일 범위](#호출-방식과-통일-범위)
- [실행 방법](#실행-방법)
- [로컬 LLM 실행](#로컬-llm-실행)
- [입출력 및 연동 문서](#입출력-및-연동-문서)
- [현재 구현 범위와 협의 항목](#현재-구현-범위와-협의-항목)
- [저장소 구성](#저장소-구성)

## 프로젝트 개요

Orchestrator는 필요한 업무에 따라 Agent를 선택하고 실행합니다. Agent는 전달받은 자료를 바탕으로 해당 업무의 결과를 생성합니다. 세 Agent 모두 의사결정을 지원하기 위한 프로토타입이며, 의료진의 판단을 대신하지 않습니다.

## Agent별 역할

| Agent | 주요 처리 | 주요 결과 |
|---|---|---|
| **Stroke Screening** | 기록과 선별 정보를 바탕으로 뇌졸중 의심 근거를 검토 | 선별 결과와 인용 근거 |
| **Clinical Summary** | 지정된 환자 자료와 질문을 바탕으로 임상 정보를 정리 | 질문별 상태·값·출처·인용 및 미확인 정보 |
| **tPA Decision Support** | 구조화된 임상 정보에 결정론적 규칙을 적용 | 규칙별 평가 결과와 검토 항목 |

Screening과 Summary는 설정된 내부 LLM을 사용할 수 있습니다. tPA는 결정론적 규칙으로 동작하며 별도 LLM을 사용하지 않습니다.

## 호출 방식과 통일 범위

세 Agent는 다음과 같은 공통 Python 진입점을 사용합니다.

```python
invoke(request, snapshot, services) -> dict
```

통일된 부분은 **호출 진입점과 인자 전달 방식**입니다. 세 Agent가 동일한 요청 본문 스키마를 사용하는 것은 아닙니다. 각 Agent의 업무와 필요한 자료가 다르므로 `request`의 필드와 반환 결과는 Agent별로 정의되어 있습니다.

Agent 선택 정보는 실행 환경의 등록 정보나 라우팅 단계에서 지정하며, 임상 요청 본문에 `agent`를 중복해 넣지 않습니다. 한 가지 작업을 수행하는 Summary 요청에는 별도의 `action`을 두지 않습니다. tPA의 `mode`는 `interim`과 `final` 평가 단계를 구분하므로 유지합니다. 구체적인 필드와 호출 위치는 [입출력 계약](docs/CONTRACT.md) 및 [연동 안내](docs/INTEGRATION.md)를 참고하십시오.

## 실행 방법

Python 3.11 이상 환경에서 저장소 루트로 이동해 실행합니다.

```bash
# Agent별 합성 입력 예제
python -m examples.run screening
python -m examples.run summary
python -m examples.run tpa

# 세 Agent 예제를 순서대로 실행
python -m examples.run all

# 전체 테스트
python -m unittest discover -s tests -v
```

합성 예제는 호출과 결과 형식을 확인하기 위한 자료이며, 실제 임상 기록에 대한 성능 또는 임상적 유효성을 의미하지 않습니다. 현재 확인한 실행 환경과 검증 범위는 [실행 확인 기록](docs/VALIDATION.md)에 정리되어 있습니다.

## 로컬 LLM 실행

Summary와 Screening은 내부에서 실행하는 로컬 모델을 사용할 수 있습니다. 모델 파일을 준비하고 각 Agent에 필요한 패키지를 설치한 뒤 실행하십시오. 추론 과정은 외부 모델 API를 사용하지 않습니다.

```bash
# Summary
python -m examples.summary --model qwen35_9b --gpu 2 --model-dir /path/to/Qwen3.5-9B
python -m examples.summary --model gemma4_12b_it --gpu 3 --model-dir /path/to/gemma-4-12B-it

# Screening
python scripts/screening_model_demo.py --model qwen35_9b --gpu 2 --model-root /path/to/models
```

의존성 및 Agent별 실행 옵션은 [Summary 안내](chain_agents/summary/README.md)와 [Screening 안내](chain_agents/screening/README.md)에 있습니다. tPA 실행에는 모델 가중치가 필요하지 않습니다.

## 입출력 및 연동 문서

| 필요한 정보 | 위치 |
|---|---|
| 공통 호출 방식, Agent별 요청·반환 필드 | [입출력 계약](docs/CONTRACT.md) |
| Orchestrator 호출 위치, Summary 자료 조회 및 추출 서비스, 결과 저장 흐름, 추가 협의 항목 | [Orchestrator 연동 안내](docs/INTEGRATION.md) |
| Screening 실행, 입력 및 반환 결과 | [Screening 안내](chain_agents/screening/README.md) |
| Summary 처리 순서, 실행 및 출력 형식 | [Summary 안내](chain_agents/summary/README.md) 및 [Summary 출력 계약](chain_agents/summary/CONTRACT.md) |
| tPA 입력, 평가 결과와 규칙 | [tPA 안내](chain_agents/tpa/README.md) 및 [평가 항목](chain_agents/tpa/ASSESSMENT.md) |
| 현재까지 확인한 실행과 그 범위 | [실행 확인 기록](docs/VALIDATION.md) |
| 현재 기본 경로에서 사용하지 않는 과거 자료 | [정리 기록](docs/archive/README.md) |

## 현재 구현 범위와 협의 항목

현재 저장소에는 Agent의 Python 호출 진입점과 각 Agent의 처리 로직이 있습니다. Summary의 자료 조회와 문서 추출은 `services.data_api` 및 `services.extractor` 인터페이스를 통해 연결하며, Screening의 추론 backend는 `services.backend`로 전달합니다. tPA는 전달된 구조화 정보를 규칙에 적용합니다.

외부 REST endpoint, 실제 병원 자료 연결, 통합 환경에서의 결과 저장 및 화면 조회는 이 저장소에서 구현하거나 검증한 범위에 포함되지 않습니다. 배포 통합을 위해 정할 항목은 Orchestrator의 요청 검증·라우팅과 Agent 입력의 연결, 조회·추출 서비스 연결, 결과 저장 및 재사용 방식입니다. 상세 내용은 [연동 안내](docs/INTEGRATION.md)에 정리되어 있습니다.

## 저장소 구성

```text
chain_agents/screening/   선별 근거 추출과 규칙
chain_agents/summary/     질문별 임상 정보와 근거 정리
chain_agents/tpa/         구조화 정보 검토 규칙과 계산
examples/                 합성 입력과 실행 예제
tests/                    입출력 계약과 규칙 확인
docs/                     연동, 입출력, 실행 확인 및 정리 기록
```
