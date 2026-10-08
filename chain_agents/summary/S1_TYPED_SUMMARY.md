# S1 typed Summary prototype

한국어 안내: [README](README.md) · [단계별 실제 처리](S1_FLOW.md) · [Mock/PDF 차이](MOCK_V012_ALIGNMENT.md) · [실제 JSON](S1_EXAMPLES.md).

Compatibility note (2026-10-08): this is the internal prototype contract, not the Mock v0.12 wire response. Confidence, confirmation status, execution metadata, and the external acceptance rules require the integration work documented in MOCK_V012_ALIGNMENT.md.

This document describes the first S1 Summary request prototype in `feature/summary`. It is the initial extraction and return step; it is not a treatment eligibility engine.

## Request, result, and storage boundary

1. The orchestrator calls the Summary Agent when the encounter enters S1. The request provides patient/encounter identifiers, input references, and stable question IDs.
2. The agent resolves only the referenced documents and structured resources.
3. Code handles structured medication, problem-list, and encounter records. The internal LLM extracts source-backed facts from narrative documents.
4. The agent validates question IDs, status/value types, evidence references, verbatim quotes, and time shape. Code assigns `not_stated` after every supplied narrative document was reviewed, and reconciles incompatible values into `conflicting` alternatives.
5. The agent returns one versioned Summary object with one final item for each expanded question.
6. The orchestrator/runtime persists the accepted result and makes its result reference available to the dashboard or a later agent. The prototype has no production persistence service; its experiment runner saves inputs, raw generations, results, and evaluation artifacts under `/data/data2/...`.

## S1 question catalog

The current request is based on the v0.12 plan's sample questions. A legacy combined question is expanded where one Boolean cannot express independent answers.

| Question ID | Value type | Meaning |
|---|---|---|
| `anticoagulant_use` | Boolean | Whether the patient is currently taking any anticoagulant. |
| `antiplatelet_use` | Boolean | Same positive/negative convention; aspirin/ASA is antiplatelet. The v0.12 sample output includes this beside anticoagulant use. |
| `recent_surgery` | Boolean | Explicit surgery in the supplied recent-history window. |
| `recent_bleeding` | Boolean | Explicit bleeding event in the supplied recent-history window. |
| `previous_stroke` | Boolean | The patient's own prior stroke/TIA, excluding family history and the current suspected event. |
| `lkw_records` | Time object | Last-known-well for the current episode, not symptom onset, discovery, or note-entry time. |

`recent_surgery_or_bleeding` expands to `recent_surgery` and `recent_bleeding`. The combined request therefore yields six final fields. The alias expansion and automatic antiplatelet addition are prototype rules and must be aligned with the orchestrator's shared contract.

## Shared output object

Every final item contains exactly:

```json
{
  "question": "anticoagulant_use",
  "status": "documented",
  "value": true,
  "evidence": [
    {
      "source_ref": "document:01",
      "quote": "현재 항응고제 apixaban 5 mg bid를 복용 중이다"
    }
  ],
  "alternatives": []
}
```

For this Boolean question, the `value` is only `true` or `false`. Drug name and dose remain visible in the evidence quote; they are not encoded in the Boolean value. If a downstream rule needs drug, dose, or last-dose time as machine-readable inputs, define those as separate question IDs before using the Summary for that decision.

### Status rules

| Status | Meaning | `value` | Evidence |
|---|---|---|---|
| `documented` | Source states an answer. For Boolean questions, explicit positive is `true`, explicit negative is `false`. | Typed non-null value | Required |
| `not_stated` | No supplied source states an answer after all referenced narrative documents are reviewed. | `null` | Empty |
| `explicitly_unknown` | A source explicitly says unknown, unavailable, unconfirmed, or not assessed. | `null` | Required |
| `conflicting` | Incompatible values for the same patient/question/time scope remain unresolved. | `null` | Empty at the parent; each `alternatives[]` value has its own evidence. |
| `not_applicable` | Reserved for a field that does not apply under an agreed scope/rule. None of the fixed initial S1 questions is currently emitted with this status. | `null` | Required if used |

`not_stated` and `explicitly_unknown` are distinct. The model emits source-backed `documented` or `explicitly_unknown` candidates and may emit full `not_stated` markers with null value and empty evidence. A marker never overrides a supported fact. Code derives `not_stated` and `conflicting` after extraction. It does not infer a negative from a missing medication, condition, or encounter row.

### Time value rules

`lkw_records.value` contains exactly `kind`, `start`, `end`, `precision`, and `original_text`.

| Kind | Endpoint shape | Use |
|---|---|---|
| `point` | `start` timestamp, `end: null` | A stated single time. |
| `approximate` | `start` normalized approximate time, `end: null` | A stated coarse/approximate time; keep the qualifier and precision. |
| `interval` | `start` lower bound and `end` upper bound | The source gives a time range. |
| `before` | `start: null`, `end` upper bound | The source says before a bound. |
| `after` | `start` lower bound, `end: null` | The source says after a bound. |
| `partial` | Date-only may use `start: YYYY-MM-DD`, `end: null`, `precision: day`; if no component can be normalized, both endpoints may be null only with `precision: unknown`. | The source has incomplete date/time detail. |

Use timezone-bearing ISO timestamps for normalized date-times. `precision` preserves whether the source specified seconds, minutes, or hours. `original_text` is a verbatim contiguous source phrase and must appear within a cited quote. The LLM never calculates a treatment window or infers treatment eligibility from LKW.

## Evidence and alternatives

- Narrative evidence is `{ "source_ref": ..., "quote": ... }`. The prompt requires a verbatim substring; the actual validator compares substrings after NFKC normalization, case folding, and whitespace removal. It is not byte-exact matching or a semantic entailment check. Multiple spans or documents are separate evidence entries.
- Structured evidence is `{ "source_ref": ..., "record": ... }`, checked against the referenced source records.
- A conflict stores `value: null`, parent `evidence: []`, and at least two distinct `{ "value", "evidence" }` alternatives. The output does not average, select, or discard unresolved source values.
- Evidence provenance checks do not establish that a quote semantically supports the extracted value; evaluation reports quote validity and overlap separately from status/value accuracy.

## Experiment and evaluation

- Eight synthetic records are re-annotated for six questions each (48 field answers).
- Each case's revised gold output is run through the code-only reconciliation path first; inference starts only if the contract reproduces the gold output.
- The current comparison uses Qwen3.5-9B and Gemma4-12B-it only, in parallel on GPU 2 (Qwen) and GPU 3 (Gemma), with one model process per GPU and greedy decoding and an 8,192-token cap. Both arms call the LLM once per case. Only fact field order changes: question/status/value/evidence versus question/evidence/status/value. The old two-stage S1 extraction path has been removed. Prior experiment files are retained as historical data, not mixed into this comparison. Actual key-order adherence and generation call counts are recorded separately from answer correctness.
- The HTML compares inputs, revised gold, each model's final JSON, raw generations, schema validation, status/value accuracy, evidence recall, source validation, tokens, and runtime.
- These are synthetic prototype cases and manually revised gold labels, not clinician-adjudicated clinical validation.

## Decision-support scope

This field catalog follows the current S1 plan example. It does not establish that these fields are sufficient for any tPA decision. Clinical decision rules should first identify which input facts affect each action or threshold, then the orchestrator should request those facts with typed values. For example, a Boolean `anticoagulant_use` alone cannot supply machine-readable drug identity or last-dose time if an agreed rule needs them. LKW, symptom onset, and symptom discovery must also remain distinct; a deterministic rule should handle time thresholds and uncertainty only after the clinical team defines that behavior.

The LLM's role in this prototype is to extract and cite recorded facts. It does not decide which threshold applies or recommend treatment.

## GT review v2

All 48 answers were reviewed against source records. Case 03 previous_stroke changed from not_stated to explicitly_unknown with the non-assessment quote. Not asked/assessed does not mean documented false. Case 05 bleeding remains not_stated; the validator now accepts a fully shaped no-mention marker. Exact required fields and verbatim quote checks still apply. Reports include all review reasons and a GT-only rescore of prior outputs.
