# 피드백 반영과 Host 통합

## 변경 대응표

| 피드백 | 구현 | 담당 경계 |
|---|---|---|
| CT 완료 시 확보 자료부터 검토 | matching completed NCCT로 source-only HITL-2 생성 | reference Host adapter |
| A03 오류/지연으로 검토 차단 금지 | 실행 상태 별도, 실패를 SUCCESS로 위장하지 않음 | Host / UI |
| 대기·기록 없음과 임상 결과 구별 | data_status / clinical_result 분리 | Agent / UI |
| 남은 시간과 불명확한 LKW | 정확한 point만 산술, 불명확하면 null | Agent |
| 수기 체중으로 재계산 | 방법·입력자·버전 Fact와 동일 계산기 | 저장은 Host |
| A02·A04·의료진 판독 활용 | A02 adapter 및 각각 별도 Fact | 실제 API mapping은 Host |
| 병력·aPTT·POCT/검사실 혈당 | 선택적 scope, 원천별 값/시각 보존 | 자료 공급은 Host |
| 기관 기준 적용 | versioned ivt_protocol 주입 | 승인은 기관/운영자 |
| 뒤늦은 결과와 판단 근거 | 열린 bundle 고정, 명시적 refresh로 새 request | Host |

## reference 통합 재현

대상: [chain-orchestrator-v03](https://github.com/donggunseo/chain-orchestrator-v03), commit `fdb382a325d52f89a46b77d50a825a08fe3ff841`에만 적용합니다. 새 디렉터리를 만들고 upstream 원본을 수정하지 않습니다. 기존 출력 디렉터리는 거부합니다.

```bash
git -c core.autocrlf=false clone https://github.com/donggunseo/chain-orchestrator-v03.git ../reference-host
git -C ../reference-host checkout fdb382a325d52f89a46b77d50a825a08fe3ff841
python -m pip install -r ../reference-host/requirements.txt
python scripts/prepare_tpa_review.py --upstream ../reference-host --output ../tpa-reference --synthetic-demo
```

`--synthetic-demo`는 복사본 registry에서 tPA를 합성 실행용 APPROVED로 표시합니다. 임상 승인과 무관합니다. 생략하면 PENDING입니다. 복사본은 tPA/common만 설치하고 reference의 Screening/Summary fixture를 유지합니다. 새 A02 모델/API를 자동 배포하지 않습니다. 파일 hash와 manifest hash도 갱신합니다.

```bash
# Linux/macOS. PowerShell에서는 cp 대신 Copy-Item 사용
cp tests/test_tpa_host.py ../tpa-reference/tpa_host_tests.py
cd ../tpa-reference
python -m unittest tpa_host_tests -v
python -m demo --backend local --test-mode --hitl recorded --recorded demo/scenarios/recorded_hitl.json --run-timeout 180 --output-dir output/tpa-review
# Agent 저장소로 돌아와 실행
python /path/to/CHAIN_agent_v0.3/scripts/verify_tpa_review_demo.py output/tpa-review
```

GitHub Actions도 동일 흐름을 실행합니다. reference의 기존 기대값에는 “final 성공 후 HITL-2”가 있어 새 semantic verifier를 사용합니다. 공개 reference에는 직접 push하지 않습니다.

합성 데모 옵션은 전체 Snapshot 관찰 polling을 5ms에서 50ms로 조정해 작은 CI runner의 Worker 경합을 줄입니다. 임상 시각·소스 발생 시점·Agent timeout·판정 규칙은 바꾸지 않습니다. CI 실패 시 합성 결과와 thread traceback을 진단용으로 남깁니다.

## 공유 계약 변경

기존 HITL request에 선택 필드 `evidence_mode: SOURCE_SNAPSHOT`을 제안합니다. 이 모드에서만 `result_ids=[]`, `results=[]`를 허용하며 HITL-2·CT 완료·CT 오더 일치를 검증합니다. 원천 Snapshot, dependencies, 허용 role, options, 필수 confirmation을 유지합니다. 다른 checkpoint에는 예외를 적용하지 않습니다.

Agent 실행과 분리하여 S2_1 진입 시 HITL-2를 만듭니다. CT 완료는 출혈 음성 판독이 아닙니다. 현재 상위 상태 진입·이벤트 처리 조건까지 재정의하지는 않습니다. 기관 프로토콜과 판독/필수 확인을 바탕으로 의료진이 결정합니다.

`EvidenceFirstEngine`을 LocalRuntime과 Temporal Workflow에 연결합니다. Temporal은 `workflow.patched("chain-tpa-evidence-first-v1")`로 기존 History 분기를 유지합니다. 실제 History replay, worker rolling deploy, 진행 중 episode 검증은 배포 전에 해야 합니다. compile/Local 테스트만으로 운영 호환성을 주장하지 않습니다.

## 늦은 결과와 새 검토

늦은 A03 결과는 latest_results / tpa_execution에 반영하되 열린 HITL snapshot/results를 바꾸지 않습니다. UI는 input_snapshot_id로 현재 검토와 같은 입력인지 구별하고 최신 결과 확인 동작을 제공해야 합니다. 새 원천 Fact가 반영되면 이전 request를 무효화하고 새 request를 엽니다. 무효화된 request의 결정은 거부합니다.

최신 결과로 새 검토를 열 때 LocalRuntime 메서드 또는 Temporal Signal `request_tpa_review_refresh`를 호출합니다. 전달 성공과 Engine 수락은 별개입니다. snapshot/audit에서 새 request 또는 HITL_REFRESH_REJECTED를 확인합니다.

```json
{
  "contract_schema": "chain-hitl-resume/v0.3",
  "command_id": "unique-refresh-command",
  "prior_request_id": "current-open-hitl-request-id",
  "actor": {"role": "NEUROLOGIST", "staff_id": "authenticated-staff-id"},
  "requested_at": "2026-10-27T09:00:00+09:00"
}
```

기존 허용 role만 사용하고 command_id는 멱등 처리합니다. 예시 시간 대신 Host 현재 시각 이하의 실제 시각을 넣습니다. Host가 인증된 actor를 넣어야 하며 클라이언트의 role 주장을 그대로 신뢰하면 안 됩니다. refresh는 이전 request를 INVALIDATED로 보존하고 새 fixed bundle을 생성합니다.

## 운영 연동에 남은 항목

- JLK의 optional HITL 필드와 빈 Agent 결과 처리, 새 결과 알림·refresh UI, v2 enum 표시.
- 기관 프로토콜/약제, 단위·유효 시간·혈당 교정 재검·확정 병력 기준의 승인과 설정 관리.
- A02 환자/내원/as-of/원문 검증과 A04·HITL-R 실제 필드/source 참조 계약.
- 수기 체중 인증·저장·감사·버전 증가, 동시 수정과 재평가 연결. 별도 DB/큐 추가 요구 없음.
- 실제 Temporal 서버/History replay, 장애·재시도·동시 결정·관측성 검증. 현재는 연구 프로토타입.

원본 피드백의 임상 화면과 환자 식별 정보는 저장소에 포함하지 않습니다.
