# Agent 호출 계약

## 공통 Python 진입점

    invoke(request, snapshot, services) -> dict

- request는 실행 mode와 Agent별 작업 정보를 담습니다.
- snapshot은 v0.3 mode가 사용하는 scoped facts입니다.
- services는 Host가 준비한 capability를 전달하는 AgentServices 객체입니다.
- 반환값은 Agent별 도메인 결과 dict이며, v0.3 결과 envelope는 Orchestrator Runtime이 구성합니다.

## Agent 요청 경로

| Agent / mode | 입력 | 결과 |
|---|---|---|
| Screening / screening | 요청과 scoped snapshot | screening_result, basis |
| Summary / s1 | episode·encounter, input_references, questions | summary-s1-fields/v1 |
| Summary / context | scoped snapshot facts | structured_context, missing_information, cache |
| tPA / interim, final | 요청과 scoped snapshot | evidence_package, assessment |

## Summary S1

S1 요청은 trigger.state_enter=S1, episode_id, encounter_id, input_references, questions를 포함합니다. 모듈 호출에서는 mode=s1, snapshot=None으로 전달합니다.

질문마다 question, status, value, evidence, alternatives를 반환합니다. evidence에는 source_ref와 원문 quote를 담습니다. status와 질문별 value 규칙은 chain_agents/summary/CONTRACT.md에 정의되어 있습니다.

## context 호환 경로

context는 기존 v0.3 starter의 요청 방식입니다. Orchestrator가 이미 구성한 snapshot facts를 읽어 구조화된 context 결과를 돌려줍니다. 자료 참조를 조회하고 질문별 근거를 구성하는 S1 경로와는 별개의 호환 mode입니다.
