# Screening v0.12 검증 기록 — 2026-10-08

검증 기준: 제공된 `mock_v0.12(2).zip`의 `files/04_agent_manifests.json`, `files/05_agent_executions.json`, `files/15_data_api_simple.json`.

- 공식 Screening 입력 7개 최상위 필드 및 중첩 문서 메타데이터 4개 필드: 일치.
- 공식 Screening 출력 16개 최상위 필드 및 `result`, `clinical_times`, `rule_trace`, `text_derived_findings`, `evidence` 중첩 구조: 일치.
- `examples/v012_screening_request.json`, `examples/v012_screening_reference_output.json`: Mock의 해당 Screening 원본 값과 동일.
- 합성 Data API 응답 3건: 원본의 해당 응답 값과 동일.
- 오프라인 unittest: 52개 통과.
- 합성 스모크: `invoke_v012()`의 `POSITIVE`, `S1`, 16개 필드 반환 확인.
- 독립 실행된 Mock HTTP stub(`localhost`)을 통한 GET + `invoke_v012()`: `POSITIVE`, `LKW=2026-10-06T13:35:00+09:00`, 근거 4건, 16개 필드 확인.
- 레거시 `agent.invoke(...)`: 기존 구현 유지. Summary/Tpa/common/문서 계약 파일 수정 없음.

**검증 범위 한계:** 테스트 모델은 고정 합성 응답을 생성합니다. GPU 모델 3종 추론, 실제 JLK Runtime 이벤트/인가/감사/UI 연동, 30초 동기 제한, 임상 정확도는 검증되지 않았습니다. Mock manifest가 참조한 `schema/stroke_screening_output_v0.1.json` 실물은 제공되지 않아 공식 JSON Schema 추가 제약에 대한 인증은 할 수 없습니다. `confidence`는 **임상적으로 보정되지 않은 evidence-coverage score**이며 확률로 사용하면 안 됩니다.
