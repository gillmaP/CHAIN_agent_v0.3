# Mock v0.12 / 160쪽 PDF와 현재 구현 대조

## API 구현 후 추가 사항

아래 본문은 typed 도메인 설계와 원안의 차이를 설명한다. 후속 JLK 연동 구현에서 다음 항목을 추가했다.
현재 실행법과 API 상태는 [API_INTEGRATION.md](API_INTEGRATION.md)를 우선한다.

- `api_service`: POST invoke, async 실행·상태 조회, SQLite 저장, GET agent-results, OpenAPI, readiness, CORS.
- `api_adapter`: bearer/timeout/redirect 차단 HTTP Data API 연결, object-shaped items와 실행 metadata를 붙이는 외부 adapter.
- 외부 profile은 `clinical-summary-integration/v1`. confidence=null, confirmation_status=UNCONFIRMED, typed_items 보존.
- 분리된 수술·출혈 질문의 resolver 목록 불일치를 수정했다.
- 120초 deadline으로 FAILED를 저장하고 late success를 거부한다. GPU 강제취소/자동 재시도는 구현하지 않았다.
- WG4 승인·실행별 JWT·scope, Event Bus 및 audit chain은 여전히 연동 대상이다.

따라서 아래의 “미구현” 표는 **도메인 단독 버전과 원안 대조**다. 위 API layer에서 해결한 항목과 나머지 플랫폼 항목을 구분한다.

확인일: 2026-10-08. 기준 문서: `CHAIN_MVP_Mock_v0.12_메인경로.pdf`(160쪽), 같은 ZIP의 Markdown 본문,
`files/04_agent_manifests.json`, `05_agent_executions.json`, `10_workflow.yaml`, `11_safety_policy.yaml`,
`13_execution_authz.json`, `14_audit_events.jsonl`, `15_data_api_simple.json`, `mock_server.py`.
쪽수는 PDF 파일의 1-based 페이지다. 구현은 `feature/summary`의 현재 S1 코드와 대조했다.

## 1. 결론

**자료 조회 경로와 S1 Summary의 역할은 원안을 따르지만, 최종 응답 계약은 변경됐다.**
현재 prototype 결과를 PDF의 `clinical_summary_output_v0.1` 응답이라고 표시하거나,
mock HTTP stub 자리에 그대로 꽂아도 된다고 설명하면 정확하지 않다.

사용자가 합의한 status/value 통일은 내부 추출과 평가를 일관되게 만들기 위한 설계 변경이다.
이 합의가 Orchestrator·Console·WG4의 외부 계약 승인까지 의미하지는 않는다.
PDF를 연동 기준으로 유지하려면 외부 adapter와 수락 규칙을 정해야 한다. 이번 작업은 차이를 문서화하며 코드를 바꾸지 않는다.

## 2. 원안을 따른 부분

| 항목 | 원안 근거 | 현재 구현 |
|---|---|---|
| 최초 S1 진입에서 과거력·약물 등 요약 | §4 p.8 이후 workflow; §8.3 pp.77–80 | S1 최초 참조형 요청을 구현 범위로 삼음. 자동 S1 전이 자체는 미구현 |
| 판단보다 근거 제공 | summary manifest §8.1 p.70 이후 | 치료 권고/처방/오더 생성 없음 |
| 입력은 참조 | §1 p.3, §8 pp.68 이후, §8.3 pp.77–78 | patient/encounter/episode, input_references, questions를 받음 |
| 요청 원형 | §8.3, `05_agent_executions.json` summary.input | 4개 원래 질문과 5개 참조를 그대로 받을 수 있음 |
| Site Data API 상대 경로 | §7 p.30 이후, §7A 실물 JSON | medications/conditions/encounters/documents의 경로·query 유지 |
| 문서 버전 지정 | 문서 `id@version`, `?version=` | ID·version·환자·내원과 대조; 최신 문서로 임의 대체하지 않음 |
| 원내 LLM | manifest INTERNAL_ON_PREM | 로컬 weights 및 offline inference |
| 코드 기반 구조화 정보 처리 | drug-class-mapper, 구조화 API flags | 이미 제공된 flags를 사용; 현 Agent에서 새 ATC mapper 구현은 안 함 |
| 근거를 함께 반환 | source_ref, 문서 quote | evidence의 source_ref/quote 또는 structured record |
| 부족 정보와 범위 제한 | missing_information, caveat | missing_information에 미확인·local coverage 제한 |
| 상태 전이/알림/처방 분리 | §4, §11 P-05/P-06 | Summary가 상태를 바꾸거나 알림/처방하지 않음 |

원안의 단순 JSON API를 사용한다. FHIR는 원안이 제공하는 대체 facade이며 현재 구현 대상이 아니다.

## 3. 의도적으로 바꾼 구조와 이유

| 항목 | Mock v0.12 예시 | 현재 S1 | 바꾼 이유 / 외부 영향 |
|---|---|---|---|
| items | 질문 ID를 key로 하는 object | `question` 필드가 있는 array | 공통 validator·순회·GT 비교 통일. Console parser 변경 또는 adapter 필요 |
| 상태 | PRESENT / NO_EVIDENCE / NONE_DOCUMENTED / CONSISTENT 등 | documented / not_stated / explicitly_unknown / conflicting / not_applicable | 사실의 긍정/부정과 정보 존재 여부 분리. enum 호환 안 됨 |
| Boolean 질문 값 | 항응고제 false, 항혈소판제는 약명 문자열 | 둘 다 true/false | 동일 질문 유형은 동일 타입. 약명/용량은 근거에 남고 독립 기계 필드로는 제공하지 않음 |
| 수술·출혈 질문 | recent_surgery_or_bleeding 하나 | recent_surgery와 recent_bleeding 둘 | 한쪽 부정으로 다른 쪽까지 부정하지 않기 위해. 외부 요청은 원래 alias를 받되 출력은 분리 |
| 항혈소판제 추가 | 원래 request에는 없으나 output에 존재 | anticoagulant 요청 시 자동 추가 | 원안 purpose/output의 관행 유지. 명시적 질문만 허용할지 계약 합의 필요 |
| LKW | timestamp 문자열 + CONSISTENT | kind/start/end/precision/original_text 시간 객체 | 근사·구간·부분 시각·정밀도 보존. 문자열만 기대하는 DSA에 직접 전달 불가 |
| 근거 | sources의 detail/as_of/quote | evidence의 quote 또는 원본 record | 근거 존재를 기계적으로 대조. source-level as_of가 자동 보존되는 것은 아님 |
| 상충 | 긍정 경로 예시에는 별도 상세 대안 구조 없음 | conflicting + alternatives | 모델이 임의로 하나를 선택하지 않고 코드가 서로 다른 값을 보존 |
| 미기록/미확인 | 예시 중심, 모든 조합 정의 없음 | not_stated와 explicitly_unknown 분리 | 침묵·미문진·명시적 부정을 구분 |
| confidence | 예시 0.9, 0.95 등 + P-07 존재 요구 | 수치 미출력, model_info에 정책 설명 | 보정/검증 없는 점수를 만들지 않음. 단, 원안 수락 규칙과 충돌함 |
| confirmation_status | UNCONFIRMED, UNCONFIRMED_TWO_SOURCES_AGREE | 없음 | 공통 다섯-key item으로 정리하면서 확인 상태를 포함하지 않음. 별도 대체 필드도 없어 **명시적 연동 공백** |
| 생성·실행 metadata | agent_id/version/execution_id, produced_time, processing_time_ms | 도메인 반환에는 없음 | Runtime 소유로 분리. 실제 외부 응답에는 Runtime 보충이 필요 |
| 치료 관련 note | 항혈소판제 항목의 “IVT 금기 아님” | 해당 문구 없음 | Summary 범위를 기록 추출로 한정 |
| missing_information | DUR 미연동, 병전 mRS 미기록 등 수기 예시 | 질문 상태와 structured 처리 한계에서 생성 | 고정 예시를 복사하지 않음. mRS는 현재 질문이 아니어서 자동 missing 판정 안 함 |

`not_applicable`은 현재 여섯 질문에서 생성하지 않고 예약만 했다. 모든 질문이 다섯 상태를 실제 사용한다는 뜻은 아니다.

### 원래 긍정 경로를 현재 형식으로 생각하면

원안 항응고제 false는 활성 처방에 없다는 설명뿐 아니라 “항응고제 복용 (-)”라는 명시적 문서 근거가 있다.
이 문서 근거로 현재 규칙의 `documented/false`를 만들 수 있다. 원안 전체를 근거 없이 부정했다고 해석하면 안 된다.
현재 코드가 막는 것은 **문서상 부정 없이 local 목록에 없다는 이유만으로 환자 전체의 false를 추론하는 것**이다.

원안 항혈소판제 값 `acetylsalicylic acid 100 mg qd`는 현재 `value:true`와 약물 record/quote로 분리된다.
`recent_surgery_or_bleeding:false`는 양쪽 모두 명시 부정일 때 각각 false가 된다.
원안 LKW의 “13:35경”과 “13:35”는 현재 모델이 approximate와 point로 구분하면, 코드가 다른 canonical value로 보고
conflicting을 만들 수 있다. **현재 코드는 같은 시계 시각이라는 이유로 근사/정확을 자동 합치지 않는다.**
이는 가능한 구조적 차이 설명이며 이번 문서화에서 원안 사례를 새로 LLM 실행한 결과는 아니다.

## 4. Transport / Tool / 플랫폼 구현 차이

| 원안 계획 | 현재 구현 | 분류 / 이후 연결 위치 |
|---|---|---|
| S1 진입 → authorize_and_run clinical_summary (async) | Python 함수 호출, 실험 runner가 직접 실행 | 플랫폼 미구현. async worker/queue가 함수 호출을 감싸야 함 |
| POST /agents/{agent_id}/invoke | 해당 HTTP route 없음 | transport 미구현. 함수 API는 내부 경계로 유지 가능 |
| Safety Gate의 1회성 토큰, scope | reader.get(path) interface와 제한된 ref만 검사 | 인증/인가 미구현. 토큰 scope 검증을 대체하지 못함 |
| Site Data API HTTPS GET | FixtureDataAPI의 dict 조회 | 자료 형식은 유지, 실제 connector 미구현 |
| manifest timeout 120s, max_retries 1 | 토큰 cap만 존재; wall-clock timeout/재시도 없음 | Runtime 연동 필요. 8192토큰은 120초 제한이 아님 |
| 정상/실패 실행 envelope | 도메인 dict 또는 예외 | Runner가 SUCCESS/FAILED와 execution ID/time/hash 구성 |
| OUTPUT_CREATED, 결과 저장 URL | 실험 output JSON 저장 | 영속 서비스 저장소/조회 endpoint 없음 |
| AGENT_RESULT_AVAILABLE, Dashboard update | 이벤트 발행 없음 | Runtime/Orchestrator/Console 연동 필요 |
| DATA_ACCESSED·hash chain audit | 실험 로그/manifest | 운영 감사 추적 미구현 |
| P-07 출력 검증 | 내부 typed validator | 같은 규약이 아님. 외부 EP4는 별도로 합의·구현 필요 |
| 문서 업데이트에 따른 재실행·캐시 | S1 참조형 함수는 매 요청 추출 | 최신화/idempotency/cache 정책은 현재 범위 밖 |

원안 p.139는 Runtime의 OUTPUT_CREATED 이후 Orchestrator의 OUTPUT_VALIDATED를 보여준다.
검사에는 schema, every_item_has_source, confirmation_status_present, exit_normal이 있다.
현재 Summary 내부 검증을 통과했다고 그 단계까지 구현된 것으로 해석하면 안 된다.

## 5. 원안 수락 규칙과 충돌하는 부분

§11 P-07은 모든 결과 항목의 source_ref, confidence·produced_time·model_info, 정상 종료 등을 요구한다.
현재 `not_stated`는 evidence가 비어야 하므로 모든 항목에 source_ref를 강제하는 규칙과 맞지 않는다.
`conflicting`도 parent evidence는 비우고 alternatives에 근거가 있다. 외부 validator가 이 구조를 이해해야 한다.
confidence와 produced_time은 현재 도메인 반환에 없고, confirmation_status도 없다.

따라서 외부 연결을 위한 두 선택지를 비교할 수 있다. **둘 다 아직 적용하지 않았다.**

1. PDF wire format 유지: 내부 typed 결과를 별도 adapter로 변환하고 실행 metadata를 Runtime에서 추가한다.
   미확인/상충·근사시간·분리 질문의 표현은 단순 key rename으로 해결되지 않는다. 허위 confidence나 false를 채워 넣으면 안 된다.
2. 외부 계약을 새 버전으로 합의: Orchestrator/Console/DSA/WG4가 typed 상태와 evidence 구조를 수락하도록 schema·manifest·정책을 함께 변경한다.
   PDF를 그대로 따르기로 했다면 이 선택을 승인 없이 구현하면 안 된다.

confirmation_status는 추출 status와 개념이 다르다. `documented`가 의사 확인 완료라는 뜻이 아니며,
동일 문서 두 개의 일치도 HITL 검증 완료로 승격하면 안 된다. Runtime/Console의 확인 상태 모델을 별도로 유지해야 한다.

## 6. 문서/원안 자체에서 확인할 불일치

| 원안 안의 차이 | 확인 근거 | 이번 문서의 처리 |
|---|---|---|
| 이벤트 표는 AGENT_EXECUTION_REQUESTED, 설명 문단은 AGENT_RUN_REQUESTED | PDF §5.3 pp.14–15, 03_outbound_events.jsonl | 표·실물의 AGENT_EXECUTION_REQUESTED를 기준 이름으로 기록. subscriber 구현 전 명칭 확정 필요 |
| manifest must_include는 result/confidence/evidence 형태, 실제 Summary는 items 안에 confidence/sources | §8.1 vs §8.3, 04/05 JSON | 실제 schema 파일이 없는 상태에서 완전한 wire schema를 추정하지 않음 |
| 감사 예시의 짧은 endpoint 표기와 §7A 실제 GET 경로가 다름 | pp.138–139 vs §7A, 15 JSON | 호출 경로는 실제 15_data_api_simple.json 및 mock_server route 기준 |
| 6개월 수술·출혈 파생값의 FHIR 매핑 설명과 canonical 응답의 개별 flags | §7A/7B | 현재 단순 JSON의 개별 행 flags 사용; FHIR 변환은 미구현 |

ZIP에 schema_ref가 가리키는 실제 `clinical_summary_output_v0.1.json` JSON Schema는 확인되지 않았다.
schema_ref의 문자열이 있다는 이유만으로 validator를 준수했다고 볼 수 없다.

## 7. 현재 코드의 추가 제약 — 변경 승인이 필요한 항목

- `trigger`/실행 상태를 확인하지 않는다. Runner가 S1 및 승인된 요청만 넘겨야 한다.
- `canonical_questions`와 resolver의 허용 질문 목록이 다르다. 분리된 수술/출혈 질문을 외부 요청에 직접 넣는 사용은 아직 지원하지 않는다.
- API `as_of`가 최초 S1 실행시각보다 뒤인 원안 fixture가 있다(구조화 응답 15:36:05, Summary 시작 15:20:06). 현재 시점 일관성 검사가 없어 time-correct replay를 검증한 실험이 아니다.
- 문서 증거의 source_ref는 버전을 보존하지만 최종 반환에 모든 문서 metadata나 구조화 source-level as_of를 별도 저장하지 않는다. 재현에는 Runtime 입력 snapshot 저장이 필요하다.
- 인용 검사는 normalized substring이지 semantic entailment 검사가 아니다.
- documented 우선 결합은 unknown evidence를 최종 결과에서 제외할 수 있다. 사건 scope나 최신성에 따른 충돌 해소는 없다.
- 현재 schema/rule 문자열과 실험 annotation/extraction-rule 버전의 표기 체계가 완전히 통합되지 않았다. 정확한 추론 재현은 run manifest와 source hash를 함께 사용한다.

이 항목들은 이번 문서화에서 조용히 수정하지 않았다. 확정 프로토타입의 동작을 그대로 설명하고, 통합 작업에서 다룰 차이로 남겼다.

## 8. 추적 가능한 근거 목록

| 확인 내용 | PDF | ZIP 파일 / 현재 코드 |
|---|---|---|
| 경계와 계약 유지 원칙 | pp.2–3, §0–1 | 메인경로 Markdown §0–1 |
| S1 분기와 비동기 Summary | §4 p.8 이후 | 10_workflow.yaml, S1.on_enter |
| 실행 이벤트 | pp.14–15, §5.3 | 03_outbound_events.jsonl |
| Data API와 토큰 | p.30 이후, §7 | 15_data_api_simple.json, mock_server.py |
| Summary manifest | p.70 이후, §8.1 | 04_agent_manifests.json:summary |
| 원래 입출력 | pp.77–80, §8.3 | 05_agent_executions.json:key=summary |
| HTTP stub | §8.5 p.92 | mock_server.py:Store.invoke; 입력 불일치여도 고정 출력 |
| 안전 정책·실행 인가 | §11 | 11_safety_policy.yaml, 13_execution_authz.json |
| 검증·저장 주체 | pp.138–139, §12 | 14_audit_events.jsonl |
| 실제 자료 조회 | 해당 없음 | mock_contract.py:requested_items/endpoint/resolve |
| 모델 입력/추론 | 해당 없음 | history_s1_extractor.py:LocalS1Extractor |
| 상태·타입·인용·결합 | 해당 없음 | history_s1_contract.py |
| 구조화 처리·최종 반환 | 해당 없음 | history_s1_summary.py |
| 실험 평가 | 해당 없음 | history_s1_experiment.py / history_s1_report.py |
