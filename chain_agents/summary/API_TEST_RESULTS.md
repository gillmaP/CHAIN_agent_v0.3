# Summary HTTP 통합 테스트 기록

실행일: 2026-10-08. 서버 166.104.110.102 / jhbak_ct.
확정 S1 프롬프트·모델·GT를 유지하고 transport·저장·adapter만 추가한 테스트다.

## 실제 모델 HTTP 왕복

| 모델 | GPU | 요청 | HTTP 결과 | LLM 호출 수 | Tool GET 수 | 확인 |
|---|---:|---|---:|---:|---:|---|
| Qwen3.5-9B | 2 | Mock v0.12 원래 요청 | 200 / SUCCESS | 1 | 5 | 항응고제 false / 항혈소판제 true; 6항목 반환 |
| Qwen3.5-9B | 2 | positive_use 합성 사례 | 200 / SUCCESS | 1 | 2 | 6/6 GT 일치 |
| Gemma4-12B-it | 3 | Mock v0.12 원래 요청 | 200 / SUCCESS | 1 | 5 | 항응고제 false / 항혈소판제 true; 6항목 반환 |
| Gemma4-12B-it | 3 | positive_use 합성 사례 | 200 / SUCCESS | 1 | 2 | 6/6 GT 일치 |

두 모델을 별도 프로세스에서 병렬 실행했다. HTTP Tool API 응답은 합성 자료이고 실제 모델이 추론했다.
POST 비동기 요청 → 자료 GET → LLM → 검증 → SQLite 저장 → GET 결과 조회 경로를 확인했다.
원래 Mock 사례는 별도 새 GT 전체 채점이 아니라 API 연결·타입·출처 검증 및 약물의 명시적 값 확인이다.
synthetic/fixture extractor를 이용한 연결 테스트와 혼동하면 안 된다.

원본 결과 및 SQLite 진단:
`/data/data2/jhbak/CHAIN_agent_summary_prototype/outputs/api_integration_20261008/`

- 모델별 `results.json`: 조회 결과, 호출 수, 자료 조회 목록, 값 검사.
- 모델별 `agent/summary.sqlite3`: 저장된 요청·실행·결과·raw generation.
- 모델별 `.log`: 실제 모델 로딩과 실행 기록.
- `exit_codes.json`: 두 프로세스 모두 0.
- `unittest.log`: 전체 자동 테스트 기록.

## 자동 테스트

최종 `python -m unittest discover -s tests -v`: **45개 통과** (기존 36개 + API 9개).

API 테스트는 실제 loopback HTTP 서버로 동기·비동기, 저장/조회/hash, idempotency/409,
4종 Data API 경로와 bearer 전달, 잘못된 요청, 자료 누락, timeout 후 late success 차단,
CORS/OpenAPI, 재시작 복구, 합성 표시, 운영 저장경로 제한을 검사한다.
이 테스트는 모델 가중치를 로드하지 않는다.

서버에서는 테스트 임시 파일도 data2에 둔다. CI에서는 임시 디렉터리에 격리하고 저장경로 guard를 테스트 안에서만 patch한다.
운영 guard 자체는 별도로 호출해 `/tmp` 같은 허용되지 않은 경로가 거부되는지 확인한다.

전체 테스트와 실제 모델 smoke는 통합 프로토타입의 동작 확인이며, WG4 인증 완료나 임상 검증 완료를 의미하지 않는다.
