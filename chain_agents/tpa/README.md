# tPA Decision Support

tPA Agent는 전달받은 구조화 임상 정보에 결정론적 규칙을 적용하고, 검토가 필요한 항목을 정리합니다. LLM이나 병원 API를 직접 호출하지 않습니다. 결과는 의료진 검토를 돕는 프로토타입이며 치료 결정이나 처방을 대신하지 않습니다.

## 호출

세 Agent는 같은 Python 진입점을 사용합니다.

```python
from chain_agents.tpa.agent import invoke

result = invoke(request, snapshot, services)
```

Orchestrator의 등록 정보 또는 API 경로가 tPA를 선택합니다. `request.mode`는 `interim` 또는 `final`을 지정합니다. 이는 평가 시점 구분에 필요합니다. 요청 본문에 `agent`나 `action`은 넣지 않습니다.

## 입력

- `request`: 평가 단계, 평가 시각, 요청과 snapshot 연결 정보
- `snapshot`: 값·상태·단위·출처·시각을 포함한 구조화 임상 facts
- `services`: 현재 tPA에서는 사용하지 않음

`interim`은 아직 수집 중인 정보를 표시하고, `final`은 전달된 정보로 다시 평가합니다. 자료가 없거나 확정되지 않으면 값을 추정하지 않고 보류 또는 의료진 확인으로 남깁니다.

## 출력

```text
mode                 요청한 평가 단계
evidence_package     평가에 전달된 facts의 복사본
assessment           규칙별 결과, 누락 정보, 검토 필요 항목, 용량 참고값
mock_only            현재 예제는 합성 데이터임을 표시
```

`assessment.status`는 `BLOCKING_FINDING_IDENTIFIED`, `INCOMPLETE_PENDING_DATA`, `PHYSICIAN_REVIEW_REQUIRED` 중 하나입니다. `dose_preview`는 계산 참고용이며 처방이나 투약 명령이 아닙니다. 세부 필드와 규칙은 [ASSESSMENT.md](ASSESSMENT.md)와 [policy.py](policy.py)를 참고하세요.

## 실행 예제

저장소 루트에서 Python 3.11 이상으로 실행합니다. 추가 패키지나 모델 가중치는 필요하지 않습니다.

```bash
python -m chain_agents.tpa.demo interim
python -m chain_agents.tpa.demo final
python -m chain_agents.tpa.demo high-bp
python -m chain_agents.tpa.demo low-platelets
python -m unittest discover -s tests -p 'test_tpa*.py' -v
```

전체 흐름에서 세 Agent를 각각 확인하려면 `python -m examples.run all`을 실행합니다. 이 예제는 Agent들을 임상 workflow로 묶지 않습니다.

## 연동 위치

Orchestrator/Host는 tPA 모듈을 등록하고, 입력 facts를 준비하며, 결과를 저장하고 화면에 전달합니다. tPA 모듈은 전달된 snapshot만 사용합니다. Python 함수가 현재 구현된 연결점이며, 이를 REST API로 감싸는 서버는 Host가 구성합니다.
