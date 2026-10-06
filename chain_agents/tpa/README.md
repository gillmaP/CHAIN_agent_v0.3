# tPA Decision Support 프로토타입

v0.3의 scoped Fact를 읽어 12개 검토 항목과 체중 기반 예상 용량을 계산합니다.
Python 3.11 이상, 표준 라이브러리만 사용하며 API 키나 추가 설치가 필요 없습니다.

```bash
python -m chain_agents.tpa.demo interim
python -m chain_agents.tpa.demo final
python -m chain_agents.tpa.demo high-bp
python -m chain_agents.tpa.demo low-platelets
python -m examples.run all
python -m unittest discover -s tests -v
```

`examples.run`의 기존 age-only 입력도 미확보 자료를 표시하며 실행됩니다.
`chain_agents.tpa.demo`는 13개 Fact를 명시적으로 만든 합성 사례입니다.
생성한 실행 JSON, 원천 병원 자료, 실제 환자 정보는 커밋하지 않습니다.

## 구현 구조

| 파일 | 책임 |
|---|---|
| `agent.py` | 기존 `invoke(request, snapshot, services)` 진입점 |
| `logic.py` | 공통 입력 경계 확인, 복사된 Fact와 도메인 결과 조합 |
| `facts.py` | 시각·수치 확인과 원본 출처를 보존하는 조회 |
| `rules.py` | I/O 없는 개별 체크 함수 |
| `dose.py` | Decimal 기반 용량 산술과 표시 반올림 |
| `policy.py` | 변경 불가능한 연구용 임계값과 한계 |
| `demo.py` | 합성 입력과 CLI 시연 |

Agent는 scope 밖의 자료를 조회하거나 LLM으로 값을 추론하지 않습니다.
입력 객체를 바꾸지 않으며 `services` 호출, 네트워크, 파일 쓰기, 상태전이를 하지 않습니다.
Runtime이 SUCCESS/FAILED envelope, 등록·hash 검증, 감사 기록을 맡고,
Orchestrator와 의료진이 HITL·알림·치료 결정을 수행합니다.

## 출력과 검토 대상

최상위 키는 기존과 같은 `mode`, `evidence_package`, `assessment`, `mock_only` 4개입니다.
`evidence_package == snapshot.facts`를 유지하고 `mock_only=True`를 명시합니다.

**이 브랜치는 `assessment`를 기존 문자열에서 구조화된 객체로 확장하는 제안입니다.**
공통 파일, Workflow 출력 목록, 등록 버전은 수정하지 않았습니다.
현재 upstream의 JSON wire validator와 출력 key 검사는 객체도 수용하지만,
문자열을 기대하는 Console/다른 소비자는 함께 검토·수정해야 합니다.
팀 검토와 등록 버전/hash 갱신 후 통합하세요. 기존 계약과 완전히 같은 결과 타입이라고
주장하지 않습니다. 자세한 제안은 [ASSESSMENT.md](ASSESSMENT.md)에 있습니다.

## 주요 동작

- 4.5시간 일반 경로 밖은 전문의 검토로 표시합니다. 선별 영상 기반 연장 경로를 자동 제외하지 않습니다.
- NCCT 완료와 오더 일치를 확인하되, 촬영 완료를 출혈 없음 판독으로 해석하지 않습니다.
- 혈소판·INR 수치, 혈압·혈당 단위, 자료 시각을 확인합니다.
- 혈압 5분 재확인은 데모 정책, 혈당 50–400은 기존 목업 기준입니다.
- 항응고제 노출은 약제·복용 시각·신기능·특이 검사 검토 대상으로 표시합니다.
- `NO_EVIDENCE`와 확인된 복용 없음은 구분하며, 고령·NIHSS·아스피린만으로 자동 제외하지 않습니다.
- PENDING/CONFLICT/ERROR/RETRACTED/INVALIDATED 등은 남아 있는 수치를 사용하지 않습니다.
- 기본 scope에 없는 수술·출혈·과거 뇌졸중·항혈소판제는 `NOT_IN_SCOPE`로 표시하고 출처를 만들지 않습니다.
- 체중이 없으면 예상 용량 options는 빈 배열입니다. 단위가 없거나 불명확한 검사는 추정하지 않습니다.
- 잘못된 수치·시각·오더 자료는 `ValueError`로 실패하며 정상 결과에 오류 객체를 넣지 않습니다.

예상 용량은 처방·투약 승인이 아닙니다. 합성 67 kg 사례는 alteplase 60.3 mg
(bolus 6.03 / infusion 54.27), TNK 16.75 mg이고 최대량은 각각 90 / 25 mg입니다.
Decimal 계산값과 0.1 mg 단위 ROUND_HALF_UP 표시값을 구분합니다.

이 프로토타입은 전체 IVT 적응증·금기 검토나 임상 검증을 대체하지 않습니다.
현재 scope로는 disabling deficit, 출혈 판독, 최근 수술/외상·활동성 출혈 등 주요 자료를
확정할 수 없으므로, 확보된 자료가 모두 있어도
최종 상태는 `PHYSICIAN_REVIEW_REQUIRED`입니다. 병원 승인 프로토콜 원문은 제공되지 않았습니다.

근거와 확인 범위는 [SOURCES.md](SOURCES.md)를 참고하세요.
