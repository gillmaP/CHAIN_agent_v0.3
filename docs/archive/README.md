# 정리한 이전 실험 자료

현재 공통 개요와 연동 방법은 저장소 루트 README에서, Agent별 상세 입출력은 각 Agent README에서 확인할 수 있습니다. 아래 항목은 이전 Mock 형식이나 별도 실험 흐름을 위한 자료였으며, 현재 세 Agent의 기본 진입점에서는 사용하지 않아 저장소에서 제거했습니다.

| 정리한 자료 | 내용 |
|---|---|
| Summary의 별도 workflow-state 경로와 관련 fixture·테스트 | 구조화 snapshot 반환 경로와 질문별 Summary 경로를 하나의 호출로 통합했습니다. 현재는 자료 참조와 질문을 받고 질문별 결과를 한 번 반환합니다. |
| Screening reference adapter, 별도 실행기와 테스트 | Mock 예시 요청을 별도 Python 함수로 변환하고 HTTP 자료 조회까지 수행하던 보조 경로. 현재 Screening은 `invoke(request, snapshot, services)`만 사용합니다. |
| Screening reference request/output/fixture JSON | 위 변환 경로의 입력·출력 예시. 현재 Agent 실행 예시는 `examples/screening_case.json`입니다. |
| 이전 Screening handoff·검증 문서 | 위 보조 경로와 예전 연동 내용을 기록한 문서. 일부 설명은 현재 공통 진입점과 맞지 않았습니다. |
| 이전 local comparison/outcome JSON | 앞선 코드 상태에서 저장한 검증 결과. 현재 브랜치의 실행 결과로 오해할 수 있어 제거했습니다. |
| Summary HTTP data client | 실제 사용되지 않던 별도 HTTP wrapper. Summary는 주입된 자료 조회 인터페이스를 사용합니다. |
| `scripts/prepare_integration.py` | 다른 checkout을 복사해 플러그인 manifest와 등록 파일을 만드는 임시 설치 스크립트. 현재 Orchestrator와 Agent 사이에 합의되지 않은 설정까지 생성해 사용 경로에서 제외했습니다. |
| `examples/run_integrated.py` | 네 Agent 호출을 한 화면에 모으던 중복 합성 실행기. 같은 확인은 `python -m examples.run all`이 담당합니다. |
| `docs/INTEGRATION.md`, `docs/CONTRACT.md` | 루트 README와 Agent 계약에 중복되던 문서. 공통 안내와 Agent별 상세 형식을 구분해 한 곳에서 관리하도록 정리했습니다. |
| 환경별 일회성 실행 기록 | 특정 실행 환경의 상태를 기록한 문서. 공유 저장소에 환경 식별 정보를 남기지 않도록 정리했습니다. |

기록에서 말하는 이전 Mock 자료는 참고용이었습니다. 현재 Agent 요청 형식과 규칙을 자동으로 결정하는 실행 계약으로 사용하지 않습니다. 삭제된 자료를 복원할 필요가 있으면 저장소의 Git 이력에서 확인할 수 있습니다.
