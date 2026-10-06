# 검증 결과 — 2026-10-06

검증한 upstream: `donggunseo/chain-orchestrator-v03` commit `00e5bf6c96b61a1a104af249b86a08d682106332`.
환경: Python 3.12, upstream requirements(Temporal Python SDK 1.31.0, PyYAML 6.x).

- starter 단위 테스트 15개 통과.
- 로컬 합성 예제 네 mode 실행 성공.
- 신규 plugin Catalog/Registry/Policy 및 설치 hash 로딩 성공: CONFIGURATION_OK.
- 세 Agent를 교체한 별도 upstream 사본에서 Local Engine recorded HITL 데모 완료.
- 최종 상태 S3, 경로 S0 → S1 → S2 → S2_1 → S3.
- State/trigger/evidence/audit 관련 upstream 사후 비교 10개 검사 통과.
- latest Screening/interim/final 결과가 신규 `0.1.0-starter` 버전의 SUCCESS임을 확인.

실제 결과: [local_outcome.json](validation/local_outcome.json), [local_comparison.json](validation/local_comparison.json).

Temporal Service/History Replay, 실제 병원 연동, 임상 모델 정확도는 검증하지 않았습니다. GitHub Actions는 설정만 제공하며, 아직 대상 원격 저장소에서 실행하지 않았습니다. Python 3.11은 CI matrix에 포함되어 있지만 이 환경에서 직접 실행한 버전은 3.12입니다.
