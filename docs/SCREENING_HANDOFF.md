# JLK 연동 요약 — Team 1 Stroke Screening / Mock v0.12

상세 계약과 실행 명령은 [`chain_agents/screening/README.md`](../chain_agents/screening/README.md)를 참고하세요. **2팀 Clinical Summary 코드는 포함하거나 수정하지 않았습니다.** 원본 프로젝트의 Summary·tPA는 유지합니다.

## JLK가 연결할 함수

`from chain_agents.screening.agent import invoke_v012`

`invoke_v012(request, *, execution_id, data_api, model, produced_time=None) -> dict`

- `request`: 공식 Mock v0.12의 Screening `input` **7개 필드** (`examples/v012_screening_request.json`)
- `execution_id`: JLK Runtime이 부여한 실행 ID (요청 JSON 7개 안에는 포함되지 않음)
- `data_api`: JLK에서 인증/인가받아 생성한 read-only Site Data API client; `.get(path)` 구현
- `model`: 로컬에서 로드된 Screening LLM (Qwen3.5/Gemma4/MedGemma), 가능하면 Runner가 재사용
- 반환값: 공식 Mock v0.12의 Screening `output` **16개 필드**를 가진 Python `dict`

**Orchestrator가 결과를 얻는 방법:** Runtime이 함수를 직접 호출해서 반환 `dict`를 받고, 이를 검증/직렬화/보관 후 `output_hash`와 `result_ref`를 만들고 `AGENT_RESULT_AVAILABLE`을 발행합니다. `scripts/screening_experiment.py`가 로컬에 저장한 결과 파일을 자동으로 읽는 구조가 아닙니다. HTTP 서버/SQLite는 구현되지 않았고 필요하지 않습니다.

## 전체 연결 흐름과 책임

1. Site Node가 `CLINICAL_DOCUMENT_UPDATED` (`ED_INITIAL_NOTE`) 발행; Orchestrator가 S0·중복 여부 확인
2. JLK/WG4가 승인된 실행 토큰/접근 범위/시간 기준을 결정하고 Runner에 주입
3. Runner가 `invoke_v012` 호출 → `HttpSiteDataAPI`로 문서 원문/내원 조회 → ID/버전/환자/해시 확인
4. LLM이 근거만 추출 → 1팀의 Python 검증/Screening 예비 판단 → 16-key dict 반환
5. JLK Runner가 결과/해시/상태/참조 저장, output event 발행; Orchestrator의 guard 충족 시만 S1 상태 전이 및 UI 알림

`structured_context`(vital_signs/poct_glucose/problem_list 등)는 **트리거 당시의 승인된 스냅샷**을 JLK Runner가 전달해야 합니다. Mock의 `/encounters/.../observations`는 시간상 최신 값이 포함될 수 있어 무조건 조회해 덮어쓰면 안 됩니다. 모델 근거 및 진단 관련 정보는 임상 검증이 필요합니다.

## 통합 시 확인할 계약 및 미완료 항목

- 원본 `mock_v0.12/files/05_agent_executions.json`의 `key=screening` 입력/출력을 `examples/v012_screening_request.json`, `examples/v012_screening_reference_output.json`으로 포함했습니다. 공식 manifest `04_agent_manifests.json`의 `screening.inputs.input_reference_only=true` 준수.
- 현재 제공된 Mock에는 `schema/stroke_screening_output_v0.1.json`이 **없습니다**. 16개 최상위·중첩 형식 비교까지 검증했으며 JSON Schema의 추가 제약 전체 충족은 인증 불가.
- `confidence`는 샘플 필드/타입을 맞추는 미보정 coverage 점수입니다. **임상 확률로 UI에 표시하거나 상태 전이 역치로 사용하는 것은 금지**하고 JLK/임상팀이 기준을 결정해야 합니다.
- `R3_NO_STRONG_ALTERNATIVE`는 제한된 문서상의 근거만 검토하며 실제 대체 진단이 없음을 보장하지 않습니다.
- Safety Gate 승인/JWT, 30초 제한·실패 처리·멱등성, Audit, `AGENT_RESULT_AVAILABLE`, `result_ref`, S1 전이, UI 연동은 **JLK/WG4 담당**이며 1팀이 구현했다고 주장하지 않습니다.
- 3개 GPU 모델의 체크포인트 파일은 저장소에 포함하지 않습니다. 실제 3모델 GPU 성공/지연·임상 정확도는 별도 검증이 필요합니다.

검증 명령: `python -m unittest discover -s tests -v` / `python scripts/screening_v012_demo.py --mode smoke`.
