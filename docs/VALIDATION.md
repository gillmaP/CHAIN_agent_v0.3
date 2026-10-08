# 통합 브랜치 확인 — 2026-10-08

브랜치: `feature/agent-integration` (세 Agent 최신 원격 브랜치 병합 후)

- 전체 단위 테스트: 107개 통과.
- `python -m examples.run all`: v0.3 합성 네 mode 성공.
- `python -m examples.run_integrated`: Screening, Summary S1, tPA interim/final 호출 성공.
- Summary S1 결과: `summary-s1-fields/v1`, 6개 합성 question items.
- 예제는 고정 합성 backend/extractor를 사용했으며 실제 LLM·병원 API·Temporal 서비스로 시험하지 않았습니다.
- upstream `AgentRuntime`에 Summary S1을 등록한 검증은 수행하지 않았습니다. 현재 request validator 및 services 주입 확장이 필요합니다.

아래는 이전 `main` starter 통합 작업의 기록이며 이번 `feature/agent-integration` 검증과 별도입니다.

---

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

## tPA 규칙 구현 후 재검증 — 2026-10-08

아래 기록은 위의 baseline 검증 이후 tPA 규칙 구현 및 최신 upstream 호환성 점검 결과입니다.
기존 링크의 JSON은 2026-10-06 baseline 결과이며 이번 실행 결과로 대체하지 않았습니다.

기준 upstream: `642f5b40525691912c685dda06043f79e37bcd1f`.
환경: Windows Python 3.12 / WSL Ubuntu 24.04 Python 3.12, Temporal SDK 1.31.0, PyYAML 6.0.3.

- 전체 단위 테스트 56개 통과. upstream의 NCCT `COMPLETED`와 항응고제 `NO_EVIDENCE` 표현을 검사하는 회귀 테스트 2개를 포함합니다.
- 새 통합 사본의 Catalog/Registry/Policy·파일 hash와 등록 entrypoint 로딩 성공.
- Windows에서 실제 AgentRuntime과 make_job으로 interim/final/high-bp/low-platelets 합성 4사례 호출 성공. 정확한 4개 도메인 key, 근거·입력 보존, 의료진 확인 요구 및 upstream Console 객체 표시를 확인했습니다.
- WSL/Linux에서 세 starter plugin을 연결한 Local Engine recorded HITL 합성 데모 완료. 최종 상태 S3, 경로 S0 → S1 → S2 → S2_1 → S3.
- upstream 비교의 흐름·원천자료·고정 근거·audit 관련 10개 검사 모두 통과. 비교기는 임상 출력·용량·임계값의 정답을 검증하지 않습니다.
- 전체 데모의 tPA final은 `0.1.0-starter` / SUCCESS이며 HITL #2의 고정 결과에 포함됩니다. NCCT는 `REQUIRES_PHYSICIAN_READ`, 항응고제 근거 없음은 `PASS_UNCONFIRMED`로 표시하고 입력 status는 보존합니다.

확인 과정에서 생성 manifest의 Windows 경로를 `/`로 통일했습니다.
upstream fixture 파일 hash는 Git 줄바꿈 변환에 영향을 받으므로 새 clone에는 `core.autocrlf=false`를 사용합니다.
확인한 upstream FixtureBackend는 허용 파일 조회에 OS별 경로 문자열을 사용하므로 Windows 전체 데모는
Screening의 `FIXTURE_NOT_INSTALLED`로 실패합니다. 전체 흐름은 upstream 코드를 수정하지 않고 WSL/Linux에서 검증했습니다.

upstream의 현재 합성 입력에는 혈압·혈당 단위 누락, NIHSS 출처 충돌, scope 밖 병력 3개 항목이 있습니다.
이를 정상값으로 보정하지 않고 의료진 검토·범위 밖으로 표시합니다. 실행 SUCCESS와 임상 검토 상태는 별개입니다.
`assessment` 문자열 → 객체와 enum의 최종 소비자 계약, JLK UI, 병원 API, 실제 Temporal Service/History Replay 및 기관 프로토콜은 추가 검토 대상입니다.
