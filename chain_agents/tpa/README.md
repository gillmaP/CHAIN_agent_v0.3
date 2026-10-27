# tPA Decision Support v2

구조화 환자 자료를 항목별로 검토하는 결정론적 Python 모듈입니다. 의료진 판단을 돕는 연구 프로토타입이며 자동 처방·투약을 하지 않습니다. 기본 설정은 RESEARCH-DEMO, mock_only=true입니다.

## 실행과 호출

Python 3.11 이상. Agent 자체에는 추가 패키지, DB, 메시지 큐, 모델, 외부 API가 필요하지 않습니다.

```bash
python -m chain_agents.tpa.demo interim
python -m chain_agents.tpa.demo final
python -m unittest discover -s tests -v
python -m chain_agents.tpa.review_demo --port 8091
```

마지막 명령은 http://127.0.0.1:8091/ 에 합성 체중 입력 화면을 엽니다. POST /weight-preview 본문은 `{"weight_kg":67,"method":"ESTIMATED"}`입니다. 동일 Python 계산기를 호출하고 저장하지 않습니다. 인증·DB·오더 연결이 없는 로컬 데모이며 제품 API가 아닙니다. 데모 입력 ID/version은 고정입니다.

```python
from chain_agents.tpa.agent import invoke
result = invoke(request, snapshot, services)
```

등록 정보/라우터가 tPA를 선택합니다. request는 mode(interim/final), evaluated_at, scope, dependencies, input_snapshot_id 등을 포함합니다. snapshot은 snapshot_id, known_at, facts입니다. [demo.py](demo.py)의 sample()이 실행 가능한 전체 입력 예시입니다. final은 호출 단계이며 자료 완비·치료 승인을 뜻하지 않습니다.

Fact에는 value, status, source_ref, source_time, known_at와 필요한 unit이 들어갑니다. scope와 Fact 키를 맞춥니다. 값이 남아 있어도 PENDING/CONFLICT이면 수치 평가에 쓰지 않습니다. 잘못된 입력은 ValueError이며 Host가 공통 실행 오류로 처리합니다.

## 입출력과 화면

| 최상위 키 | 역할 |
|---|---|
| mode | 요청 단계 |
| evidence_package | 입력 snapshot.facts와 같은 내용의 독립 복사본. 별도 Tool/API 호출 없음 |
| assessment | prototype-v2 구조화 검토 결과 |
| mock_only | 현재 항상 true |

checks는 자료 상태(data_status)와 임상 검토 상태(clinical_result)를 분리합니다. INR 검사 대기는 PENDING / NOT_ASSESSED입니다. 항응고제 기록 없음은 NO_RECORD이며 확정적 미복용이 아닙니다. display에는 한국어 표시와 정렬 priority가 있습니다. 배열 순서는 유지하고 UI에서 priority로 정렬할 수 있습니다.

기존 result, aggregate assessment.status, check ID는 호환용으로 유지합니다. ID의 숫자는 기존 식별자이며 실제 기준은 label과 protocol_parameters를 읽습니다. **aggregate와 Agent SUCCESS를 HITL 열기·치료 시행 gate로 쓰면 안 됩니다.** 상세 계약은 [ASSESSMENT.md](ASSESSMENT.md), Host 연결과 변경 대응표는 [INTEGRATION.md](INTEGRATION.md)를 보세요.

기본 12항목에 더해 scope에 있으면 aPTT, 과거 두개내출혈, A04 영상 결과, 의료진 NCCT 판독, 항응고제 상세를 추가 표시합니다. POCT/검사실 혈당, 수술/출혈 병력도 각각 보존합니다. A04의 false나 CT 촬영 완료만으로 출혈 없음·치료 가능을 확정하지 않습니다.

## 시간창과 체중

time_window는 LKW와 evaluated_at으로 경과·마감·남은 초를 계산합니다. ISO 시각과 A02의 {kind,start,end,precision,original_text}를 받습니다. 정확한 point의 분/초 정밀도만 countdown을 계산합니다. 대략·구간·이전·이후·날짜만 알려진 시각은 UNCERTAIN, 미확보는 UNKNOWN이며 남은 시간은 null입니다. 표준 시간창 경과는 전체 치료 불가 판정이 아닙니다. 화면은 평가 시각을 표시하고 새 평가와 함께 갱신해야 합니다.

manual.weight_facts()/weight_preview()는 체중, 방법, 입력자, entry ID, version, recorded_at을 검증합니다. 방법은 MEASURED, PATIENT_REPORTED, CAREGIVER_REPORTED, ESTIMATED입니다. 기존 체중에 방법이 없으면 UNKNOWN입니다. Host가 인증·저장·버전 증가·재평가를 담당합니다. 체중 미확보 시 용량을 반환하지 않습니다.

## 기관 프로토콜

services.ivt_protocol에 [policy.Policy](policy.py) 또는 허용된 필드의 dict를 주입합니다. 미제공 시 연구 기본값입니다. ID, version, approval_status와 전체 파라미터를 결과에 기록합니다. SITE_APPROVED 선언은 site_id·approved_by·별도 protocol_id를 요구하지만, 코드가 실제 임상 승인을 증명하지는 않습니다. 운영자가 승인된 설정의 출처와 변경 권한을 관리해야 합니다. 승인 설정을 주입해도 현재 mock_only=true를 유지합니다.

연구 임계값 밖 결과는 REVIEW_REQUIRED로 표시합니다. 기관 설정에서도 CONDITION_MET는 **개별 수치 조건 해당**이며 전체 치료 금기가 아닙니다. 혈압·혈당 교정 후 재평가, 항응고제 종류/마지막 복용/신기능, 장애성 증상과 영상 기반 연장 경로는 의료진·기관 프로토콜 검토가 필요합니다. [SOURCES.md](SOURCES.md)

## A02 / A04 / Host 연결

summary_adapter.summary_facts()는 검증된 A02 summary-items/v1의 질문별 값을 Fact로 변환합니다. episode/encounter와 Host가 공급한 A02 source_ref·버전·source_time·known_at을 확인합니다. merge_summary()는 독립 Snapshot을 만들며 확보된 원천값을 기록 없음으로 덮어쓰지 않습니다. 상충 값과 양쪽 출처는 별도 _alternatives Fact에 남깁니다. 원문 인용/대안은 summary_evidence Fact로 보존합니다.

Host는 A02 입력의 환자·문서 원본·인용 검증, as-of cutoff, 접근 권한, scope 확장 및 hash/dependencies 재생성을 담당합니다. adapter가 A02 API를 호출하거나 공통 envelope를 자동 변환하지 않습니다. A04와 HITL-R은 각각 a04_hemorrhage, physician_ncct_read Fact로 각자의 출처를 붙여 전달합니다. 실제 A04 payload mapping은 JLK와 합의해야 합니다.

## CT 완료 후 HITL-2

[orchestrator.py](orchestrator.py)는 특정 공개 reference Engine용 opt-in adapter입니다. standalone Agent가 import하지 않습니다. [INTEGRATION.md](INTEGRATION.md)에 재현 명령과 공유 계약 변경을 정리했습니다.

참조 Host는 CT 완료와 오더 일치를 확인하면 Agent 결과 없이도 현재 원천 Snapshot으로 HITL-2를 엽니다. 실패/timeout을 정상 결과로 바꾸지 않습니다. 의료진 role과 필수 확인 항목을 유지합니다. 늦은 Agent 결과는 열린 근거를 바꾸지 않고 명시적 refresh가 새 request를 만듭니다. 새 원천 Fact는 이전 request를 무효화하고 새 Snapshot 검토를 만듭니다.

Temporal, Activity, 이벤트 수집, Context, 결과 저장, 감사 이력, 알림, DB/큐는 Host/JLK 책임입니다. 이 모듈은 별도 DB/큐를 추가하지 않습니다. Local Engine 실행과 Host 테스트는 CI에 포함합니다. 실제 Temporal 서버·운영 History replay·JLK UI 배포 검증은 별도입니다.

## 코드 구성

| 파일 | 책임 |
|---|---|
| agent.py / logic.py | 진입점 / 결과 조립 |
| facts.py / rules.py | 자료 검증 / 항목별 규칙 |
| policy.py / timing.py / dose.py | 설정 / 시간 산술 / 용량 산술 |
| presentation.py | 화면용 상태와 표시 우선순위 |
| summary_adapter.py / manual.py | A02 및 수기 체중을 Fact로 연결 |
| orchestrator.py | opt-in reference Host의 HITL 동작 |
| review_demo.py / weight_demo.html | 로컬 합성 체중 입력 예제 |
