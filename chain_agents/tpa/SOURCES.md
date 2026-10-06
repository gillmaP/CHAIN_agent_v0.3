# 조사 근거와 적용 범위

확인일: 2026-10-06. 연구용 프로토타입의 참고 근거이며 기관 승인 프로토콜이 아닙니다.

| ID | 1차 자료 | 적용과 확인 범위 |
|---|---|---|
| AHA2026 | [AHA/ASA 2026 지침 공식 요약](https://professional.heart.org/en/science-news/2026-guideline-for-the-early-management-of-patients-with-acute-ischemic-stroke/top-things-to-know) | 일반 4.5시간 경로, disabling deficit 평가, 선별된 영상 기반 연장 경로. 저널 본문은 403으로 접근하지 못했으며 공식 요약을 사용 |
| ESO2021 | [ESO IVT guideline 원문](https://journals.sagepub.com/doi/10.1177/2396987321989865) | PICO 8·11·12·13: 고령, 혈압, 항혈전제, 검사/수술. 최신 AHA 전체 지침으로 표현하지 않음 |
| ACTIVASE_LABEL | [Activase prescribing information, DailyMed](https://dailymed.nlm.nih.gov/dailymed/fda/fdaDrugXsl.cfm?setid=c669f77c-fa48-478b-a14b-80b20a0139c2&type=display) | Alteplase AIS 용량 0.9 mg/kg, 최대 90 mg, 10% bolus와 나머지 60분 infusion. 미국 라벨의 3시간과 지침의 4.5시간을 구분 |
| KSS2025 | [대한뇌졸중학회 TNK 과학적 성명](https://pmc.ncbi.nlm.nih.gov/articles/PMC12411285/) | TNK 0.25 mg/kg 계산 참고. 출판사/검색 색인 내용 확인, PMC 본문은 CAPTCHA로 전체 접근 불가 |
| CHAIN_MOCK | 전달받은 CHAIN MVP Mock v0.12, §8.1·§8.4·§8.4′·§11 | 12개 체크 ID, strict BP 경계와 혈당 50–400 예시. 독립적인 임상 근거는 아님 |

v0.3 실행 계약은 저장소의 [docs/CONTRACT.md](../../docs/CONTRACT.md),
[upstream 고정 revision](https://github.com/donggunseo/chain-orchestrator-v03/tree/00e5bf6c96b61a1a104af249b86a08d682106332)
기준입니다. v0.12의 HTTP 참조 기반 호출, 고정 2회 호출, 자체 Runtime은 옮기지 않았습니다.

혈압 자료의 5분 freshness는 로컬 데모 정책입니다. 전체 금기, 영상 판독,
disabling deficit, 항응고제별 특이 검사·복용 시각·신기능은 의료진 확인 대상입니다.
대한뇌졸중학회 웹 지침 페이지의 오래된 2012 제외 조건을 현재 공통 규칙으로 복사하지 않았습니다.
