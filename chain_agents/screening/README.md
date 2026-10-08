# Stroke Screening Agent

Screening은 Orchestrator가 지정한 기록과 구조화된 선별 정보를 읽고, 인용 가능한 근거에 prototype rule을 적용합니다. 결과는 검토 지원용이며 진단이나 치료 결정을 대신하지 않습니다.

## 공통 호출

```python
from chain_agents.screening.agent import invoke

result = invoke(request, snapshot, services)
```

`request`에는 실행 ID, 허용 범위와 평가 시각이 들어가고 `snapshot`에는 그 범위 안의 문서와 구조화 facts가 들어갑니다. `services.backend`는 고정 합성 결과 또는 `ScreeningLLMBackend`를 제공합니다.

기본 합성 실행:

```bash
python -m examples.run screening
```

실제 로컬 모델을 공통 `invoke` 진입점으로 실행:

```bash
python scripts/screening_model_demo.py --model qwen35_9b --gpu 2 --model-root /path/to/models
```

모델은 `chain_agents/screening/local_model.py`가 로컬 가중치에서 불러옵니다. 추론 중 Hub나 외부 모델 API를 호출하지 않습니다.

## 반환 결과

현재 plugin 결과는 `screening_result`, `mock_only`, `basis`입니다. `basis`에는 선별 결과에 사용한 문서 근거가 포함됩니다. 모델 결과가 불확실하거나 필수 근거가 없으면 오류로 종료하며 이를 `NEGATIVE`로 바꾸지 않습니다.

```json
{
  "screening_result": "POSITIVE",
  "mock_only": false,
  "basis": [
    "focal_weakness [document:NOTE-01@1]: Rt. U/E G2, Rt. L/E G3"
  ]
}
```

## 실행 확인

```bash
python -m unittest discover -s tests -p 'test_screening*.py' -v
```

모델 비교용 합성 평가 도구는 `scripts/screening_experiment.py evaluate`입니다. Agent 연동 예제는 `scripts/screening_model_demo.py`이며, 두 실행은 모두 저장소 루트에서 시작합니다.
