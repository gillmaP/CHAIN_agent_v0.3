# 실제 요청·LLM 입력·출력 예시

기준일 2026-10-08. 새 추론을 실행한 문서가 아니라 확정 실행의 저장 결과와 현재 입력 구성 코드를 대조한 문서다.

## 1. Mock v0.12 원래 Summary 요청

PDF §8.3 pp.77–78 / 05_agent_executions.json summary.input 원문이다.

```json
{
  "episode_id": "EP-HYG-261006-058",
  "encounter_id": "E261006058",
  "patient_id": "PT-HYG-edd5a27af1",
  "trigger": {
    "state_enter": "S1",
    "cause_event_id": "EVT-HYG-261006-004874"
  },
  "input_references": [
    "medication:active",
    "condition:problem_list",
    "encounter_history:6m",
    "document:DOC-2610060412@1",
    "document:DOC-2610060403@2"
  ],
  "questions": [
    "anticoagulant_use",
    "recent_surgery_or_bleeding",
    "previous_stroke",
    "lkw_records"
  ]
}
```

## 2. Mock v0.12 원래 응답

현재 출력과 혼동하지 않도록 원래 fixture 응답을 그대로 싣는다.

```json
{
  "agent_id": "clinical-summary-agent",
  "agent_version": "0.2.0",
  "execution_id": "EXE-HYG-261006-0142",
  "episode_id": "EP-HYG-261006-058",
  "encounter_id": "E261006058",
  "items": {
    "anticoagulant_use": {
      "status": "NO_EVIDENCE",
      "value": false,
      "confidence": 0.9,
      "sources": [
        {
          "source_ref": "medication:active",
          "detail": "활성 처방 4종 중 항응고제 계열(B01AA/B01AE/B01AF) 없음",
          "as_of": "2026-09-22"
        },
        {
          "source_ref": "document:DOC-2610060412@1",
          "quote": "항응고제 복용 (-) : 보호자 확인 및 본원 처방내역상 없음"
        }
      ],
      "caveat": "타원 처방·비급여 약물은 미확인 — 보호자 재확인 권고",
      "confirmation_status": "UNCONFIRMED"
    },
    "antiplatelet_use": {
      "status": "PRESENT",
      "value": "acetylsalicylic acid 100 mg qd",
      "confidence": 0.95,
      "sources": [
        {
          "source_ref": "medication:active",
          "detail": "아스피린프로텍트정100mg (B01AC06), 최근 조제 2026-09-22"
        }
      ],
      "note": "IVT 금기 아님 — 정보 제공용"
    },
    "recent_surgery_or_bleeding": {
      "status": "NO_EVIDENCE",
      "value": false,
      "confidence": 0.85,
      "sources": [
        {
          "source_ref": "encounter_history:6m",
          "detail": "6개월 내 내원 2건(외래 내분비내과 2026-07-14, 2026-09-22), 입원·수술·시술 없음"
        },
        {
          "source_ref": "document:DOC-2610060412@1",
          "quote": "최근 수술력, 출혈력 없음(보호자 진술)"
        }
      ],
      "caveat": "타원 수술·시술 이력은 본원 기록에 없음",
      "confirmation_status": "UNCONFIRMED"
    },
    "previous_stroke": {
      "status": "NONE_DOCUMENTED",
      "value": false,
      "confidence": 0.9,
      "sources": [
        {
          "source_ref": "condition:problem_list",
          "detail": "I6x 코드 없음"
        },
        {
          "source_ref": "document:DOC-2610060412@1",
          "quote": "Stroke/TIA (-)"
        }
      ]
    },
    "lkw_records": {
      "status": "CONSISTENT",
      "value": "2026-10-06T13:35:00+09:00",
      "confidence": 0.92,
      "sources": [
        {
          "source_ref": "document:DOC-2610060412@1",
          "quote": "13:35경 딸과 전화통화 시까지 특이증상 없었다고 함"
        },
        {
          "source_ref": "document:DOC-2610060403@2",
          "quote": "마지막 정상 확인 13:35 (딸과 통화)"
        }
      ],
      "confirmation_status": "UNCONFIRMED_TWO_SOURCES_AGREE"
    }
  },
  "missing_information": [
    "타원 처방 조회(DUR) 미연동",
    "병전 mRS 미기록"
  ],
  "produced_time": "2026-10-06T15:21:14+09:00",
  "processing_time_ms": 67580,
  "model_info": {
    "rule_set": "drug-class-mapper v0.1",
    "nlp_model": "chain-ko-clinical-ner v0.2.1 (on-prem)",
    "llm_tier": "INTERNAL_ON_PREM"
  }
}
```

## 3. 확정 실험에서 실제 사용한 요청과 질문

실험 root: `/data/data2/jhbak/CHAIN_agent_summary_prototype/outputs/summary_s1_gt_review_parallel_20261008_v2`

모델: Gemma4-12B-it, method=direct, case=`01_positive_use`. 원안 환자와 다른 합성 사례다.

```json
{
  "episode_id": "EP-01_positive_use",
  "encounter_id": "ENC-01_positive_use",
  "patient_id": "SYN-01_positive_use",
  "trigger": {
    "state_enter": "S1"
  },
  "input_references": [
    "document:01_positive_use-1@1",
    "document:01_positive_use-2@1"
  ],
  "questions": [
    "anticoagulant_use",
    "antiplatelet_use",
    "recent_surgery_or_bleeding",
    "previous_stroke",
    "lkw_records"
  ]
}
```

## 4. 실제 system prompt

코드의 DIRECT_PROMPT와 저장된 direct_prompt.txt가 동일함을 확인했다. 아래 문구 전체가 system 메시지다.

```text
You extract facts for the initial S1 Clinical Summary. Work only from the supplied narrative documents and fixed question catalog. Return only one JSON object with exactly: {"facts": [...], "reviewed_documents": [...]}.
Each fact has EXACTLY question, status, value, evidence. Each evidence entry has EXACTLY source_ref and quote. Do not output an assertion/polarity property.

STATUS RULES:
- documented: the source explicitly provides a value. A documented negative is status=documented with value=false for boolean questions. A documented positive is status=documented with value=true. These rules are identical for anticoagulant_use and antiplatelet_use.
- explicitly_unknown: the source explicitly says unknown, unavailable, could not be confirmed, not asked, or not assessed (모름, 확인 불가, 미문진, 문진하지 않음, 다루지 않음). Use value=null and cite that statement. This is not a denial of the clinical condition. Never convert a statement about not asking or not knowing into documented/false.
- not_stated: no supplied document addresses the question at all after every document is reviewed. You may omit the fact or emit the full four-key fact with status=not_stated, value=null, evidence=[]. Never omit required keys in an emitted fact. Code reconciles this marker with other facts and structured sources; a supported documented or explicitly_unknown fact takes precedence over a no-mention marker. An explicit statement of non-assessment is explicitly_unknown, not not_stated.
- Do NOT emit conflicting. Keep each incompatible source statement as its own documented fact; code compares values and creates conflict alternatives.
- Do NOT emit not_applicable for this question set.

QUESTION-SPECIFIC RULES:
- Boolean values must be JSON true or false, never strings such as "present"/"absent", never 0/1. Do not infer false from silence or from a local medication/problem list having no matching row.
- recent_surgery and recent_bleeding are separate questions. A negative answer to one says nothing about the other. Do not merge them.
- previous_stroke means this patient's past stroke/TIA. Exclude relatives and the current suspected episode.
- lkw_records means last known well for the current episode, not symptom onset, discovery/recognition, or note-entry time. Return a time object with EXACTLY kind, start, end, precision, original_text. Kinds: point, approximate, interval, before, after, partial. Precision: second, minute, hour, day, unknown. Timestamps must include timezone. Shape rules are strict: point -> start=timestamp,end=null; approximate -> start=normalized approximate timestamp,end=null; interval -> start=lower bound,end=upper bound; before -> start=null,end=upper bound; after -> start=lower bound,end=null; partial date-only -> start=YYYY-MM-DD,end=null,precision=day. Use both null endpoints only for partial with precision=unknown and preserve the phrase in original_text. Do not put the same point in both start and end. For a minute-level time, format seconds as :00 and set precision=minute. For an hour-level approximate time such as "오늘 15시쯤", use 15:00:00 with precision=hour and kind=approximate; this does not claim an exact 15:00. Preserve approximation/range; never invent exactness. original_text must be a verbatim contiguous phrase from the source. Use the document date to resolve relative dates only when supplied by saved_time/document context.
- If multiple documents agree on one value, you may emit one fact with multiple evidence entries. If they disagree about the same patient/question/time scope, keep separate facts with their own evidence. Do not treat resolved historical changes or different events as conflicts.

EVIDENCE RULES:
- Copy verbatim, contiguous text from the cited source. Use enough context for negation, person, current/past status, and time. If multiple separated sentences are needed, use multiple evidence entries; do not splice text or translate.
- source_ref must exactly match an input reference. reviewed_documents must list every supplied document reference exactly once, including documents with no relevant statement.
- Use only the fixed question IDs supplied. Do not answer unrequested concepts. Do not include confidence, prose, derived clinical conclusions, or treatment recommendations.

Question definitions (including each answer type) are supplied in the user message.
Emit each fact's keys in the order listed above.
```

## 5. 실제 user 메시지 JSON

저장된 입력 사례와 실제 코드의 _question_specs/documents 구성으로 재구성했다. GT는 들어가지 않는다. 다음 JSON 문자열을 user.content로 넣는다. token ID dump는 아니며 chat template은 모델 processor가 적용한다.

```json
{
  "questions": [
    {
      "question": "anticoagulant_use",
      "type": "boolean",
      "value_schema": "JSON boolean only: true means an explicit current-use statement; false means an explicit current non-use statement. For documented use a boolean, never a drug name. For explicitly_unknown or not_stated use null, following the common status rules.",
      "scope": "Whether this patient is currently taking any anticoagulant.",
      "rules": "true=explicit current use; false=explicit current non-use. Drug name/dose are evidence, not this value. Exclude family members and discontinued drugs."
    },
    {
      "question": "antiplatelet_use",
      "type": "boolean",
      "value_schema": "JSON boolean only: true means an explicit current-use statement; false means an explicit current non-use statement. For documented use a boolean, never a drug name. For explicitly_unknown or not_stated use null, following the common status rules.",
      "scope": "Whether this patient is currently taking any antiplatelet medication.",
      "rules": "Use the same boolean convention as anticoagulant_use. Aspirin/ASA is antiplatelet, not anticoagulant. Exclude family members and discontinued drugs."
    },
    {
      "question": "recent_surgery",
      "type": "boolean",
      "value_schema": "JSON boolean only: true or false. null is allowed only when status is explicitly_unknown or another non-documented status.",
      "scope": "Whether this patient had surgery within the recent-history window stated by the source/request (default six months for this S1 prototype).",
      "rules": "true/false requires explicit evidence. Do not use a denial of surgery to answer recent_bleeding."
    },
    {
      "question": "recent_bleeding",
      "type": "boolean",
      "value_schema": "JSON boolean only: true or false. null is allowed only when status is explicitly_unknown or another non-documented status.",
      "scope": "Whether this patient had a bleeding event within the recent-history window stated by the source/request (default six months for this S1 prototype).",
      "rules": "true/false requires explicit evidence. Do not use a denial of bleeding to answer recent_surgery."
    },
    {
      "question": "previous_stroke",
      "type": "boolean",
      "value_schema": "JSON boolean only: true or false. null is allowed only when status is explicitly_unknown or another non-documented status.",
      "scope": "Whether this patient personally had a past stroke or TIA.",
      "rules": "Exclude family history and the current suspected stroke episode. Explicitly stated no history is false."
    },
    {
      "question": "lkw_records",
      "type": "time",
      "value_schema": {
        "exact_keys": [
          "kind",
          "start",
          "end",
          "precision",
          "original_text"
        ],
        "timestamp_format": "Use YYYY-MM-DDTHH:MM:SS+09:00 for Korean local date-times. A minute-level time uses seconds :00 and precision=minute; an hour-level time uses :00:00 and precision=hour. Preserve the source precision.",
        "kind_shapes": {
          "point": "start=the normalized timestamp; end=null; precision reflects the source.",
          "approximate": "start=the normalized approximate timestamp (for example 15시쯤 -> 15:00:00 with precision=hour); end=null; retain the qualifier in original_text.",
          "interval": "start=the lower-bound timestamp; end=the upper-bound timestamp; precision reflects the source.",
          "before": "start=null; end=the stated upper-bound timestamp.",
          "after": "start=the stated lower-bound timestamp; end=null.",
          "partial": "For a known date without a known time, use start=YYYY-MM-DD, end=null, precision=day. If no component can be normalized, both endpoints may be null only when precision=unknown; preserve the supplied phrase in original_text."
        },
        "original_text": "Copy the shortest contiguous verbatim source phrase that states the LKW value, including approximation or range wording. Do not paraphrase."
      },
      "scope": "The last-known-well time for the current episode, when the patient was last known at their neurologic baseline.",
      "rules": "Do not substitute symptom onset, discovery/recognition time, or note-entry time. Preserve approximate/interval precision and the original wording. Multiple agreeing sources become one documented value with multiple evidence entries; incompatible times become conflicting alternatives. For point and approximate values, end must be null; only interval uses both endpoints."
    }
  ],
  "documents": [
    {
      "source_ref": "document:01_positive_use-1@1",
      "saved_time": "2026-10-08T19:30:00+09:00",
      "text": "2026-10-08. 환자는 현재 항응고제 apixaban 5 mg bid를 복용 중이다. 항혈소판제로 아스피린 100mg qd도 현재 복용한다. 최근 6개월 수술과 출혈은 모두 없었다. 환자는 2021년 뇌졸중 병력이 있다. 마지막 정상 확인 시각은 오늘 09:10이다. 증상 발견은 10:00이다."
    },
    {
      "source_ref": "document:01_positive_use-2@1",
      "saved_time": "2026-10-08T19:30:00+09:00",
      "text": "2026-10-08 간호기록. 딸에게 확인한 마지막 정상 시각은 오늘 09:10이다. 증상 발견 10:00."
    }
  ]
}
```

## 6. Gemma가 실제 생성한 raw 응답

저장된 generation.raw를 그대로 싣는다. 사람이 재작성한 모범 답안이 아니다.

```text
```json
{
  "facts": [
    {
      "question": "anticoagulant_use",
      "status": "documented",
      "value": true,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "환자는 현재 항응고제 apixaban 5 mg bid를 복용 중이다."
        }
      ]
    },
    {
      "question": "antiplatelet_use",
      "status": "documented",
      "value": true,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "항혈소판제로 아스피린 100mg qd도 현재 복용한다."
        }
      ]
    },
    {
      "question": "recent_surgery",
      "status": "documented",
      "value": false,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "최근 6개월 수술과 출혈은 모두 없었다."
        }
      ]
    },
    {
      "question": "recent_bleeding",
      "status": "documented",
      "value": false,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "최근 6개월 수술과 출혈은 모두 없었다."
        }
      ]
    },
    {
      "question": "previous_stroke",
      "status": "documented",
      "value": true,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "환자는 2021년 뇌졸중 병력이 있다."
        }
      ]
    },
    {
      "question": "lkw_records",
      "status": "documented",
      "value": {
        "kind": "point",
        "start": "2026-10-08T09:10:00+09:00",
        "end": null,
        "precision": "minute",
        "original_text": "오늘 09:10"
      },
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "마지막 정상 확인 시각은 오늘 09:10이다."
        },
        {
          "source_ref": "document:01_positive_use-2@1",
          "quote": "딸에게 확인한 마지막 정상 시각은 오늘 09:10이다."
        }
      ]
    }
  ],
  "reviewed_documents": [
    "document:01_positive_use-1@1",
    "document:01_positive_use-2@1"
  ]
}
```
```

## 7. 검증된 모델 후보 payload

```json
{
  "facts": [
    {
      "question": "anticoagulant_use",
      "status": "documented",
      "value": true,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "환자는 현재 항응고제 apixaban 5 mg bid를 복용 중이다."
        }
      ]
    },
    {
      "question": "antiplatelet_use",
      "status": "documented",
      "value": true,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "항혈소판제로 아스피린 100mg qd도 현재 복용한다."
        }
      ]
    },
    {
      "question": "recent_surgery",
      "status": "documented",
      "value": false,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "최근 6개월 수술과 출혈은 모두 없었다."
        }
      ]
    },
    {
      "question": "recent_bleeding",
      "status": "documented",
      "value": false,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "최근 6개월 수술과 출혈은 모두 없었다."
        }
      ]
    },
    {
      "question": "previous_stroke",
      "status": "documented",
      "value": true,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "환자는 2021년 뇌졸중 병력이 있다."
        }
      ]
    },
    {
      "question": "lkw_records",
      "status": "documented",
      "value": {
        "kind": "point",
        "start": "2026-10-08T09:10:00+09:00",
        "end": null,
        "precision": "minute",
        "original_text": "오늘 09:10"
      },
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "마지막 정상 확인 시각은 오늘 09:10이다."
        },
        {
          "source_ref": "document:01_positive_use-2@1",
          "quote": "딸에게 확인한 마지막 정상 시각은 오늘 09:10이다."
        }
      ]
    }
  ],
  "reviewed_documents": [
    "document:01_positive_use-1@1",
    "document:01_positive_use-2@1"
  ]
}
```

## 8. 코드 결합 후 실제 최종 반환

모델 후보 네 key에 alternatives를 추가하고 질문마다 하나로 결합한 결과다. 구조화 근거가 있으면 원본 record를 포함한다.

```json
{
  "schema_version": "summary-s1-fields/v1",
  "episode_id": "EP-01_positive_use",
  "encounter_id": "ENC-01_positive_use",
  "input_references": [
    "document:01_positive_use-1@1",
    "document:01_positive_use-2@1"
  ],
  "questions": [
    "anticoagulant_use",
    "antiplatelet_use",
    "recent_surgery",
    "recent_bleeding",
    "previous_stroke",
    "lkw_records"
  ],
  "items": [
    {
      "question": "anticoagulant_use",
      "status": "documented",
      "value": true,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "환자는 현재 항응고제 apixaban 5 mg bid를 복용 중이다."
        }
      ],
      "alternatives": []
    },
    {
      "question": "antiplatelet_use",
      "status": "documented",
      "value": true,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "항혈소판제로 아스피린 100mg qd도 현재 복용한다."
        }
      ],
      "alternatives": []
    },
    {
      "question": "recent_surgery",
      "status": "documented",
      "value": false,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "최근 6개월 수술과 출혈은 모두 없었다."
        }
      ],
      "alternatives": []
    },
    {
      "question": "recent_bleeding",
      "status": "documented",
      "value": false,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "최근 6개월 수술과 출혈은 모두 없었다."
        }
      ],
      "alternatives": []
    },
    {
      "question": "previous_stroke",
      "status": "documented",
      "value": true,
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "환자는 2021년 뇌졸중 병력이 있다."
        }
      ],
      "alternatives": []
    },
    {
      "question": "lkw_records",
      "status": "documented",
      "value": {
        "kind": "point",
        "start": "2026-10-08T09:10:00+09:00",
        "end": null,
        "precision": "minute",
        "original_text": "오늘 09:10"
      },
      "evidence": [
        {
          "source_ref": "document:01_positive_use-1@1",
          "quote": "마지막 정상 확인 시각은 오늘 09:10이다."
        },
        {
          "source_ref": "document:01_positive_use-2@1",
          "quote": "딸에게 확인한 마지막 정상 시각은 오늘 09:10이다."
        }
      ],
      "alternatives": []
    }
  ],
  "missing_information": [],
  "model_info": {
    "rule_set": "summary-s1-reconcile/v1",
    "llm_tier": "INTERNAL_ON_PREM",
    "model_key": "gemma4_12b_it",
    "extraction_method": "direct",
    "confidence_policy": "No uncalibrated confidence score is emitted."
  },
  "mock_only": true
}
```

## 9. 이 사례의 GT

평가기만 사용하는 정답이며 LLM 입력에는 포함하지 않았다.

```json
[
  {
    "question": "anticoagulant_use",
    "status": "documented",
    "value": true,
    "evidence": [
      {
        "source_ref": "document:01_positive_use-1@1",
        "quote": "현재 항응고제 apixaban 5 mg bid를 복용 중이다"
      }
    ],
    "alternatives": []
  },
  {
    "question": "antiplatelet_use",
    "status": "documented",
    "value": true,
    "evidence": [
      {
        "source_ref": "document:01_positive_use-1@1",
        "quote": "항혈소판제로 아스피린 100mg qd도 현재 복용한다"
      }
    ],
    "alternatives": []
  },
  {
    "question": "recent_surgery",
    "status": "documented",
    "value": false,
    "evidence": [
      {
        "source_ref": "document:01_positive_use-1@1",
        "quote": "최근 6개월 수술과 출혈은 모두 없었다"
      }
    ],
    "alternatives": []
  },
  {
    "question": "recent_bleeding",
    "status": "documented",
    "value": false,
    "evidence": [
      {
        "source_ref": "document:01_positive_use-1@1",
        "quote": "최근 6개월 수술과 출혈은 모두 없었다"
      }
    ],
    "alternatives": []
  },
  {
    "question": "previous_stroke",
    "status": "documented",
    "value": true,
    "evidence": [
      {
        "source_ref": "document:01_positive_use-1@1",
        "quote": "환자는 2021년 뇌졸중 병력이 있다"
      }
    ],
    "alternatives": []
  },
  {
    "question": "lkw_records",
    "status": "documented",
    "value": {
      "kind": "point",
      "start": "2026-10-08T09:10:00+09:00",
      "end": null,
      "precision": "minute",
      "original_text": "오늘 09:10"
    },
    "evidence": [
      {
        "source_ref": "document:01_positive_use-1@1",
        "quote": "마지막 정상 확인 시각은 오늘 09:10이다"
      },
      {
        "source_ref": "document:01_positive_use-2@1",
        "quote": "마지막 정상 시각은 오늘 09:10이다"
      }
    ],
    "alternatives": []
  }
]
```

## 10. 실행 metadata

```json
{
  "revision": "707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7",
  "runtime": {
    "python_version": "3.11.10",
    "transformers_version": "5.19.0",
    "torch_version": "2.8.0+cu126",
    "torchaudio_version": "2.8.0+cu126",
    "tokenizers_version": "0.23.2",
    "safetensors_version": "0.8.0",
    "huggingface_hub_version": "1.33.0",
    "cuda_version": "12.6",
    "gpu_requested": "3",
    "pid": 699835,
    "model_device_map": {},
    "gpu_name_visible_as_0": "NVIDIA RTX A6000"
  },
  "failure": null,
  "generation_calls": 1,
  "generated_tokens": 734,
  "cap_reached": false
}
```
