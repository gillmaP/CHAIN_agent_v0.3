"""Synthetic-only, offline Summary LLM experiment.

Kept separate from logic.run(): CHAIN v0.3 has no narrative output field and
requires structured_context to equal the input snapshot facts.
"""
from __future__ import annotations

import json
import os
import statistics
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "qwen35_9b"
MODELS = {
    "qwen35_9b": {"repo_id": "Qwen/Qwen3.5-9B", "revision": "c202236235762e1c871ad0ccb60c8ee5ba337b9a", "directory": "Qwen3.5-9B", "license": "Apache-2.0", "parameter_label": "9B"},
    "qwen25_14b_instruct": {"repo_id": "Qwen/Qwen2.5-14B-Instruct", "revision": "cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8", "directory": "Qwen2.5-14B-Instruct", "license": "Apache-2.0", "parameter_label": "14B", "loader": "causal"},
    "gemma4_12b_it": {"repo_id": "google/gemma-4-12B-it", "revision": "707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7", "directory": "gemma-4-12B-it", "license": "Apache-2.0", "parameter_label": "12B"},
    "medgemma15_4b_it": {"repo_id": "google/medgemma-1.5-4b-it", "revision": "91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b", "directory": "medgemma-1.5-4b-it", "license": "HAI-DEF Terms of Use", "parameter_label": "4B"},
}
PROMPT_VERSION = "clinical-summary-structured-v2.2"
DATA_DEFAULT = "/data/data2/jhbak/CHAIN_agent_summary_prototype"
DATA_ROOTS = (Path("/data/data2"), Path("/data/data3"))
CONCEPTS = frozenset({
    "symptom.left_arm_weakness", "symptom.right_arm_weakness",
    "symptom.facial_droop", "symptom.dysarthria", "symptom.visual_change",
    "symptom.headache", "diagnosis.stroke", "time.symptom_onset",
    "time.last_known_well", "history.hypertension", "history.stroke",
    "medication.anticoagulant", "vital.blood_pressure", "lab.glucose",
})
CATEGORIES = {"symptom", "timeline", "diagnosis", "history", "medication", "vital", "lab", "imaging", "exam", "other"}
SUBJECTS = {"patient", "family_member", "other", "unknown"}
REPORTERS = {"patient", "family_member", "coworker", "ems", "clinician", "patient_and_family", "not_stated"}
STATUSES = {"present", "absent", "uncertain", "explicitly_unknown", "recorded"}
TEMPORALITIES = {"current", "historical", "planned", "unknown"}
EVENT_TIME_KINDS = {"symptom_onset", "last_known_well", "last_dose", "discovered", "measured_at", "other"}
ITEM_REQUIRED = {"category", "concept", "subject", "status", "temporality", "source"}
ITEM_OPTIONAL = {"subject_detail", "reported_by", "value", "unit", "event_time", "event_time_kind"}
SOURCE_FIELDS = {"document_id", "documented_at", "quote"}


def experiment_root(create=False):
    path = Path(os.environ.get("CHAIN_SUMMARY_DATA_DIR", DATA_DEFAULT)).resolve()
    if not any(path == root or root in path.parents for root in DATA_ROOTS):
        raise ValueError("Store model and run files under /data/data2 or /data/data3.")
    if create:
        path.mkdir(parents=True, exist_ok=True)
        for name in ("models", "hf_cache", "outputs"):
            (path / name).mkdir(exist_ok=True)
    return path


def _doc(doc_id, documented_at, text):
    return {"id": doc_id, "documented_at": documented_at, "text": text}


def _fact(category, concept, subject, reported_by, status, temporality, doc, evidence,
          *, value=None, unit=None, event_time=None, event_time_kind=None,
          subject_detail=None):
    item = {
        "category": category, "concept": concept, "subject": subject,
        "reported_by": reported_by, "status": status, "temporality": temporality,
        "source": {
            "document_id": doc["id"],
            "documented_at": doc["documented_at"],
            "quote": evidence,
        },
    }
    if subject_detail is not None:
        item["subject_detail"] = subject_detail
    if value is not None:
        item["value"] = value
    if unit is not None:
        item["unit"] = unit
    if event_time is not None:
        item["event_time"] = event_time
    if event_time_kind is not None:
        item["event_time_kind"] = event_time_kind
    return item


def synthetic_cases():
    """Hand-authored notes; no patient files are read."""
    er = _doc(
        "ER-001", "2026-10-06T14:12:00+09:00",
        "2026-10-06 14:12 응급실 기록. 마지막 정상 확인(last known well)은 12:55. "
        "오후 1시 40분부터 왼쪽 팔에 힘이 빠짐. facial droop와 dysarthria는 없다고 함.",
    )
    neuro = _doc(
        "NEURO-002", "2026-10-06T18:20:00+09:00",
        "2026-10-06 18:20 신경과 기록. Possible stroke, r/o ischemic event. "
        "말 어눌함(dysarthria)이 있는지는 환자도 확실히 모르겠다고 함. "
        "시야 이상은 없다고 보고함. 환자 과거력(PMH): hypertension. "
        "아버지는 70세에 stroke 병력이 있음. 환자는 현재 두통이 없다고 함.",
    )
    meds = _doc(
        "MEDS-003", "2026-10-06T19:30:00+09:00",
        "2026-10-06 19:30 약물 및 검사 확인. 현재 복용약: apixaban 5 mg twice daily. "
        "마지막 복용은 2026-10-05 22:00. BP 148/86 mmHg, random glucose 132 mg/dL. "
        "마지막 정상 시각(LKW)은 환자와 보호자가 알지 못해 확인 불가.",
    )
    family = _doc(
        "WITNESS-A", "2026-10-06T08:30:00+09:00",
        "2026-10-06 08:30 보호자 기록: 가족은 증상 발생 시각을 오전 7시 55분이라고 기억함.",
    )
    coworker = _doc(
        "WITNESS-B", "2026-10-06T08:33:00+09:00",
        "2026-10-06 08:33 구급대 기록: 동료는 증상 시작이 08:15였다고 목격 진술함.",
    )
    return [
        {
            "case_id": "ko_en_timing_negation",
            "documents": [er],
            "expected": [
                _fact("timeline", "time.last_known_well", "patient", "not_stated",
                      "recorded", "historical", er, "마지막 정상 확인(last known well)은 12:55",
                      event_time="2026-10-06T12:55:00+09:00",
                      event_time_kind="last_known_well"),
                _fact("symptom", "symptom.left_arm_weakness", "patient", "not_stated",
                      "present", "current", er, "오후 1시 40분부터 왼쪽 팔에 힘이 빠짐",
                      event_time="2026-10-06T13:40:00+09:00",
                      event_time_kind="symptom_onset"),
                _fact("symptom", "symptom.facial_droop", "patient", "not_stated",
                      "absent", "current", er, "facial droop와 dysarthria는 없다고 함"),
                _fact("symptom", "symptom.dysarthria", "patient", "not_stated",
                      "absent", "current", er, "facial droop와 dysarthria는 없다고 함"),
            ],
        },
        {
            "case_id": "uncertainty_person_history",
            "documents": [neuro],
            "expected": [
                _fact("diagnosis", "diagnosis.stroke", "patient", "clinician",
                      "uncertain", "current", neuro, "Possible stroke, r/o ischemic event"),
                _fact("symptom", "symptom.dysarthria", "patient", "patient",
                      "uncertain", "current", neuro,
                      "말 어눌함(dysarthria)이 있는지는 환자도 확실히 모르겠다고 함"),
                _fact("symptom", "symptom.visual_change", "patient", "patient",
                      "absent", "current", neuro, "시야 이상은 없다고 보고함"),
                _fact("history", "history.hypertension", "patient", "not_stated",
                      "present", "historical", neuro, "환자 과거력(PMH): hypertension"),
                _fact("history", "history.stroke", "family_member", "not_stated",
                      "present", "historical", neuro, "아버지는 70세에 stroke 병력이 있음",
                      value="stroke at age 70", subject_detail="father"),
                _fact("symptom", "symptom.headache", "patient", "patient",
                      "absent", "current", neuro, "환자는 현재 두통이 없다고 함"),
            ],
        },
        {
            "case_id": "medication_values_unknown_lkw",
            "documents": [meds],
            "expected": [
                _fact("medication", "medication.anticoagulant", "patient", "not_stated",
                      "present", "current", meds,
                      "현재 복용약: apixaban 5 mg twice daily. 마지막 복용은 2026-10-05 22:00",
                      value="apixaban 5 mg twice daily",
                      event_time="2026-10-05T22:00:00+09:00",
                      event_time_kind="last_dose"),
                _fact("vital", "vital.blood_pressure", "patient", "not_stated",
                      "recorded", "current", meds, "BP 148/86 mmHg",
                      value="148/86", unit="mmHg"),
                _fact("lab", "lab.glucose", "patient", "not_stated",
                      "recorded", "current", meds, "random glucose 132 mg/dL",
                      value="132", unit="mg/dL"),
                _fact("timeline", "time.last_known_well", "patient", "patient_and_family",
                      "explicitly_unknown", "historical", meds,
                      "마지막 정상 시각(LKW)은 환자와 보호자가 알지 못해 확인 불가"),
            ],
        },
        {
            "case_id": "conflicting_onset_times",
            "documents": [family, coworker],
            "expected": [
                _fact("timeline", "time.symptom_onset", "patient", "family_member",
                      "recorded", "historical", family,
                      "증상 발생 시각을 오전 7시 55분이라고 기억함",
                      event_time="2026-10-06T07:55:00+09:00",
                      event_time_kind="symptom_onset"),
                _fact("timeline", "time.symptom_onset", "patient", "coworker",
                      "recorded", "historical", coworker,
                      "증상 시작이 08:15였다고 목격 진술함",
                      event_time="2026-10-06T08:15:00+09:00",
                      event_time_kind="symptom_onset"),
            ],
        },
    ]


SYSTEM_PROMPT = f"""You extract source-grounded clinical facts for a research prototype.
Use only the supplied synthetic notes. Do not diagnose, recommend treatment, calculate
eligibility, or infer undocumented facts.

Return one JSON object with exactly two keys: summary and items. Write summary in
concise Korean. Each item is one clinical finding, timeline entry, measurement, history, or medication.
Keep the patient as subject when another person reports the patient's symptoms: put
that person in reported_by. reported_by is the person whose statement is explicitly
described, not the author of the note. If the speaker is not stated, omit reported_by; the parser defaults it to
not_stated. The note author is not the reporter. Use family_member as the subject for family history and put the normalized
relationship code father or mother in subject_detail. Preserve different reports as separate items; do not choose one
version of a conflict. Keep a medication, its full name and dose/frequency in value, and a stated
last-dose time in event_time on one medication item; do not split it. Do not use unit
for medication dose. Use unit only for vital/lab measurements. Preserve qualifiers
such as laterality and age in value when stated. Keep ambiguous r/o wording neutral;
do not turn it into a definite diagnosis or exclusion.

Each item must have these fields:
category, concept, subject, status, temporality, source.
Optional fields are subject_detail, reported_by, value, unit, event_time, event_time_kind.
If reported_by is not provided, the parser sets it to not_stated.
Allowed category values: symptom, timeline, diagnosis, history, medication, vital,
lab, imaging, exam, other.
Allowed subjects: patient, family_member, other, unknown.
Allowed reported_by values: patient, family_member, coworker, ems, clinician,
patient_and_family, not_stated.
Allowed status values: present, absent, uncertain, explicitly_unknown, recorded.
Allowed temporality values: current, historical, planned, unknown.
The source object must contain exactly document_id, documented_at, quote. Copy
document_id and documented_at from the cited input document. quote must be an exact
substring from that document.

For symptoms, diagnoses, histories, and medications, use present, absent, uncertain,
or explicitly_unknown. Use absent only for an explicit negative statement. Use
uncertain for possible, suspected, or unclear findings. Use explicitly_unknown only
when a note says the information is unknown or cannot be determined. Use recorded
only for timeline entries and vital/lab measurements. If an item is not mentioned,
do not invent it or generate a checklist of every allowed concept. This experiment
has no fixed required-item checklist. Include value for the medication dose/frequency
and unit only for a stated vital or lab measurement. Omit optional fields when they
do not apply; never output null.

event_time is the time of the clinical event, not note-entry time. Use ISO-8601 with
the explicit timezone when the date and time are clear. event_time_kind identifies
what the time means, such as symptom_onset, last_known_well, last_dose, discovered,
or measured_at. Never substitute source.documented_at for event_time. Preserve
numbers and units. Do not add unsupported facts.

Allowed concepts: {", ".join(sorted(CONCEPTS))}
Return no markdown fences or extra fields."""


def build_user_prompt(case):
    data = {"case_id": case["case_id"], "documents": case["documents"]}
    return (
        "Extract a source-grounded clinical summary. These records are synthetic. "
        "documented_at is when the note was entered, not event time.\n"
        + json.dumps(data, ensure_ascii=False, indent=2)
    )


def _norm(value):
    if value is None:
        return ""
    return "".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def _hashable(value):
    try:
        hash(value)
        return value
    except TypeError:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _is_time_fact(item):
    concept = item.get("concept")
    return (isinstance(concept, str) and concept.startswith("time.")) or item.get("event_time") is not None


def _signature(item):
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    return tuple(_hashable(value) for value in (
        item.get("category"), item.get("concept"), item.get("subject"),
        item.get("subject_detail"), item.get("status"), item.get("temporality"),
        item.get("event_time"), item.get("event_time_kind"), source.get("document_id"),
    ))


def _quote_supported(quote, text):
    return bool(quote.strip()) and _norm(quote) in _norm(text)


def validate_result(result, documents):
    errors = []
    if not isinstance(result, dict):
        return ["result must be a JSON object"]
    if set(result) != {"summary", "items"}:
        errors.append("result must have exactly summary and items")
    if not isinstance(result.get("summary"), str) or not result.get("summary", "").strip():
        errors.append("summary must be non-empty text")
    if not isinstance(result.get("items"), list):
        return errors + ["items must be a list"]

    docs = {doc["id"]: doc for doc in documents}
    allowed_fields = ITEM_REQUIRED | ITEM_OPTIONAL
    for i, item in enumerate(result["items"]):
        where = f"items[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{where} must be an object")
            continue
        keys = set(item)
        if not ITEM_REQUIRED <= keys or not keys <= allowed_fields:
            errors.append(f"{where} fields do not match schema")
            continue
        if item["category"] not in CATEGORIES:
            errors.append(f"{where}.category invalid")
        if item["concept"] not in CONCEPTS:
            errors.append(f"{where}.concept invalid")
        if item["subject"] not in SUBJECTS:
            errors.append(f"{where}.subject invalid")
        if item["status"] not in STATUSES:
            errors.append(f"{where}.status invalid")
        if item["temporality"] not in TEMPORALITIES:
            errors.append(f"{where}.temporality invalid")
        if "subject_detail" in item and (
            not isinstance(item["subject_detail"], str) or not item["subject_detail"].strip()
        ):
            errors.append(f"{where}.subject_detail must be non-empty text")
        if "reported_by" in item and item["reported_by"] not in REPORTERS:
            errors.append(f"{where}.reported_by invalid")
        if item["subject"] == "family_member" and not item.get("subject_detail"):
            errors.append(f"{where}.subject_detail is required for family_member")
        if item["subject"] != "family_member" and "subject_detail" in item:
            errors.append(f"{where}.subject_detail is only for family_member")
        if "value" in item and (
            not isinstance(item["value"], str) or not item["value"].strip()
        ):
            errors.append(f"{where}.value must be non-empty text when present")
        if "unit" in item and (
            not isinstance(item["unit"], str) or not item["unit"].strip()
        ):
            errors.append(f"{where}.unit must be non-empty text when present")
        if "unit" in item and "value" not in item:
            errors.append(f"{where}.unit requires value")
        if item["status"] in {"absent", "explicitly_unknown"} and "value" in item:
            errors.append(f"{where}.value must be omitted for {item['status']}")
        if item["status"] == "recorded" and item["category"] not in {"timeline", "vital", "lab"}:
            errors.append(f"{where}.recorded is only for timeline and measurements")
        if item["status"] == "recorded" and "value" not in item and "event_time" not in item:
            errors.append(f"{where}.recorded item needs value or event_time")
        if "unit" in item and item["category"] not in {"vital", "lab"}:
            errors.append(f"{where}.unit is only for vital or lab measurements")
        if item["status"] == "explicitly_unknown" and "event_time" in item:
            errors.append(f"{where}.event_time must be omitted for explicitly_unknown")
        if "event_time" in item:
            try:
                parsed_time = datetime.fromisoformat(item["event_time"].replace("Z", "+00:00"))
                if parsed_time.tzinfo is None:
                    errors.append(f"{where}.event_time must include an offset")
            except (ValueError, AttributeError):
                errors.append(f"{where}.event_time must be ISO-8601 with an offset")
            if "event_time_kind" not in item:
                errors.append(f"{where}.event_time_kind is required with event_time")
        if "event_time_kind" in item and item["event_time_kind"] not in EVENT_TIME_KINDS:
            errors.append(f"{where}.event_time_kind invalid")
        if "event_time_kind" in item and "event_time" not in item:
            errors.append(f"{where}.event_time_kind requires event_time")
        source = item["source"]
        if not isinstance(source, dict) or set(source) != SOURCE_FIELDS:
            errors.append(f"{where}.source fields do not match schema")
            continue
        doc_id = source["document_id"]
        if not isinstance(doc_id, str) or doc_id not in docs:
            errors.append(f"{where}.source.document_id is not in input")
        else:
            if source["documented_at"] != docs[doc_id]["documented_at"]:
                errors.append(f"{where}.source.documented_at does not match input")
        quote = source["quote"]
        if not isinstance(quote, str) or not quote.strip():
            errors.append(f"{where}.source.quote must be a quote")
        elif isinstance(doc_id, str) and doc_id in docs and not _quote_supported(quote, docs[doc_id]["text"]):
            errors.append(f"{where}.source.quote is not present in cited document")
        elif isinstance(doc_id, str) and doc_id in docs and "event_time" in item:
            try:
                event_time = datetime.fromisoformat(item["event_time"].replace("Z", "+00:00"))
                note_time = datetime.fromisoformat(source["documented_at"].replace("Z", "+00:00"))
                if event_time == note_time:
                    explicit_time = event_time.strftime("%Y-%m-%d %H:%M")
                    explicit_iso = event_time.isoformat(timespec="minutes")
                    if _norm(explicit_time) not in _norm(quote) and _norm(explicit_iso) not in _norm(quote):
                        errors.append(f"{where}.event_time duplicates note-entry time without an explicit quote")
            except (ValueError, AttributeError):
                pass
    return errors


def parse_and_validate(raw, documents):
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        return None, [f"invalid_json: {exc}"]
    if isinstance(result, dict) and isinstance(result.get("items"), list):
        for item in result["items"]:
            if isinstance(item, dict):
                item.setdefault("reported_by", "not_stated")
    return result, validate_result(result, documents)


def _fact_label(item):
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    parts = [
        str(item.get("concept")), str(item.get("status")),
        f"subject={item.get('subject')}", f"reported_by={item.get('reported_by')}",
    ]
    if item.get("event_time"):
        parts.append(f"time={item['event_time']}")
    if item.get("value") is not None:
        parts.append(f"value={item.get('value')} {item.get('unit', '')}".strip())
    parts.append(f"doc={source.get('document_id')}")
    return "; ".join(parts)


def _time_key(item):
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    return tuple(_hashable(value) for value in (
        item.get("concept"), item.get("subject"), source.get("document_id"),
    ))


def score_predictions(cases, predictions):
    by_case = {item["case_id"]: item for item in predictions}
    total = len(cases)
    json_valid = sum(bool(by_case.get(c["case_id"], {}).get("json_valid")) for c in cases)
    schema_valid = sum(bool(by_case.get(c["case_id"], {}).get("schema_valid")) for c in cases)
    gold, predicted = set(), set()
    gold_value, predicted_value = {}, {}
    gold_reporter, predicted_reporter = {}, {}
    gold_times, predicted_times = {}, {}
    fact_count = grounded = summaries = 0
    case_breakdown = {}

    for case in cases:
        docs = {doc["id"]: doc for doc in case["documents"]}
        expected = case["expected"]
        for item in expected:
            key = _signature(item)
            gold.add(key)
            gold_value[key] = (_norm(item.get("value")), _norm(item.get("unit")))
            gold_reporter[key] = item.get("reported_by", "not_stated")
            if _is_time_fact(item):
                gold_times[_time_key(item)] = (
                    item.get("status"), item.get("event_time"), item.get("event_time_kind")
                )

        prediction = by_case.get(case["case_id"], {})
        result = prediction.get("parsed")
        actual_items = result.get("items", []) if isinstance(result, dict) else []
        if not prediction.get("json_valid") or not isinstance(actual_items, list):
            actual_items = []
        if prediction.get("schema_valid") and isinstance(result, dict):
            summaries += bool(result.get("summary", "").strip())

        case_gold = {_signature(item) for item in expected}
        case_pred = set()
        for item in actual_items:
            if not isinstance(item, dict):
                continue
            fact_count += 1
            source = item.get("source") if isinstance(item.get("source"), dict) else {}
            doc = docs.get(source.get("document_id"))
            quote = source.get("quote")
            if doc and isinstance(quote, str) and _quote_supported(quote, doc["text"]):
                grounded += 1
            key = _signature(item)
            predicted.add(key)
            case_pred.add(key)
            predicted_value[key] = (_norm(item.get("value")), _norm(item.get("unit")))
            predicted_reporter[key] = item.get("reported_by")
            if _is_time_fact(item):
                predicted_times[_time_key(item)] = (
                    item.get("status"), item.get("event_time"), item.get("event_time_kind")
                )
        reporter_mismatches = [
            {
                "fact": _fact_label(item),
                "expected_reported_by": item.get("reported_by"),
                "predicted_reported_by": predicted_reporter.get(_signature(item)),
            }
            for item in expected
            if _signature(item) in case_pred
            and gold_reporter.get(_signature(item)) != predicted_reporter.get(_signature(item))
        ]
        case_breakdown[case["case_id"]] = {
            "expected_count": len(case_gold),
            "predicted_count": len(case_pred),
            "matched_count": len(case_gold & case_pred),
            "reporter_mismatches": reporter_mismatches,
            "missing": [_fact_label(item) for item in expected if _signature(item) not in case_pred],
            "extra": [
                _fact_label(item) for item in actual_items
                if isinstance(item, dict) and _signature(item) not in case_gold
            ],
            "schema_errors": prediction.get("schema_errors", []),
            "summary": result.get("summary") if isinstance(result, dict) else None,
        }

    tp, fp, fn = len(gold & predicted), len(predicted - gold), len(gold - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    aligned = gold & predicted
    reporter_correct = sum(gold_reporter.get(key) == predicted_reporter.get(key) for key in aligned)
    runtimes = [float(p["generation_seconds"]) for p in predictions if p.get("generation_seconds") is not None]
    time_exact = sum(gold_times[key] == predicted_times.get(key) for key in gold_times)
    return {
        "synthetic_dataset_version": "synthetic-stroke-summary-v1",
        "prompt_version": PROMPT_VERSION,
        "total_cases": total,
        "valid_json_rate": json_valid / total if total else 0.0,
        "valid_schema_rate": schema_valid / total if total else 0.0,
        "summary_present_rate": summaries / schema_valid if schema_valid else 0.0,
        "quote_support_rate": grounded / fact_count if fact_count else 0.0,
        "fact_precision": precision, "fact_recall": recall, "fact_f1": f1,
        "value_and_unit_exact_rate_on_aligned_facts": (
            sum(gold_value[k] == predicted_value[k] for k in aligned) / len(aligned) if aligned else None
        ),
        "reporter_accuracy_on_aligned_facts": (
            reporter_correct / len(aligned) if aligned else None
        ),
        "time_fact_exact_rate": time_exact / len(gold_times) if gold_times else None,
        "fact_score_policy": (
            "Set-based signatures compare category, concept, subject, subject_detail, "
            "status, temporality, event time/kind, and source document. Reporter, "
            "value/unit, and exact source quotation are scored separately."
        ),
        "fact_count": fact_count, "expected_facts": len(gold),
        "median_generation_seconds": statistics.median(runtimes) if runtimes else None,
        "case_breakdown": case_breakdown,
    }


def model_config(model_key):
    try:
        return MODELS[model_key]
    except KeyError as exc:
        raise ValueError(f"Unknown model {model_key!r}; choose one of {sorted(MODELS)}") from exc


def download_model(model_key=DEFAULT_MODEL):
    spec = model_config(model_key)
    root = experiment_root(create=True)
    from huggingface_hub import get_token, snapshot_download
    auth_token = get_token()
    os.environ["HF_HOME"] = str(root / "hf_cache")
    os.environ["HF_HUB_CACHE"] = str(root / "hf_cache" / "hub")
    model_dir = root / "models" / spec["directory"]
    snapshot_download(
        repo_id=spec["repo_id"], revision=spec["revision"], token=auth_token,
        local_dir=str(model_dir), cache_dir=str(root / "hf_cache" / "hub"),
    )
    manifest = {
        "model_key": model_key, "model_id": spec["repo_id"],
        "revision": spec["revision"], "license": spec["license"],
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_directory": str(model_dir), "weights_stored_in_git": False,
    }
    (root / "models" / f"{model_key}.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + chr(10), encoding="utf-8",
    )
    print(f"Downloaded {spec['repo_id']} at {spec['revision']} to {model_dir}")


class LocalModel:
    def __init__(self, model_key, model_dir, gpu_index="0", max_new_tokens=1800):
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_index)
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; this experiment expects a local GPU.")
        self.model_key = model_key
        self.spec = model_config(model_key)
        self.torch, self.model_dir, self.max_new_tokens = torch, model_dir, max_new_tokens
        if self.spec.get("loader") == "causal":
            from transformers import AutoModelForCausalLM, AutoTokenizer
            processor_class, model_class = AutoTokenizer, AutoModelForCausalLM
        else:
            from transformers import AutoModelForMultimodalLM, AutoProcessor
            processor_class, model_class = AutoProcessor, AutoModelForMultimodalLM
        started = time.perf_counter()
        self.processor = processor_class.from_pretrained(str(model_dir), local_files_only=True)
        self.model = model_class.from_pretrained(
            str(model_dir), local_files_only=True, device_map="auto",
            dtype="auto", low_cpu_mem_usage=True,
        )
        self.model.eval()
        self.load_seconds = time.perf_counter() - started

    def generate(self, case):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(case)},
        ]
        template_options = {
            "add_generation_prompt": True, "tokenize": True, "return_dict": True,
            "return_tensors": "pt",
        }
        if self.model_key == "qwen35_9b":
            template_options["enable_thinking"] = False
        inputs = self.processor.apply_chat_template(messages, **template_options).to(self.model.device)
        self.torch.cuda.synchronize()
        started = time.perf_counter()
        with self.torch.inference_mode():
            output = self.model.generate(
                **inputs, max_new_tokens=self.max_new_tokens, do_sample=False, use_cache=True,
            )
        self.torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        generated = output[0, inputs["input_ids"].shape[-1]:]
        return self.processor.decode(generated, skip_special_tokens=True).strip(), elapsed, int(generated.shape[-1])

    def metadata(self, gpu_index):
        gpu = self.torch.cuda.get_device_properties(0)
        return {
            "model_key": self.model_key, "model_id": self.spec["repo_id"],
            "model_revision": self.spec["revision"], "license": self.spec["license"],
            "parameter_label": self.spec["parameter_label"],
            "model_path": str(self.model_dir), "prompt_version": PROMPT_VERSION,
            "transformers_version": __import__("transformers").__version__,
            "torch_version": self.torch.__version__, "cuda_runtime_version": self.torch.version.cuda,
            "gpu_index_requested": str(gpu_index), "gpu_name": gpu.name,
            "gpu_total_memory_bytes": gpu.total_memory, "model_load_seconds": self.load_seconds,
            "offline_inference": True, "synthetic_only": True,
        }


def run_experiment(gpu_index="0", max_new_tokens=1800, case_limit=None, model_key=DEFAULT_MODEL):
    spec = model_config(model_key)
    root = experiment_root(create=True)
    model_dir = root / "models" / spec["directory"]
    if not (model_dir / "config.json").is_file():
        raise FileNotFoundError(f"Missing model at {model_dir}; run download --model {model_key} first.")
    cases = synthetic_cases()
    if case_limit is not None:
        if case_limit < 1:
            raise ValueError("case_limit must be at least 1")
        cases = cases[:case_limit]
    model = LocalModel(model_key, model_dir, gpu_index, max_new_tokens)
    predictions = []
    for case in cases:
        raw, elapsed, tokens = "", None, 0
        try:
            raw, elapsed, tokens = model.generate(case)
            parsed, errors = parse_and_validate(raw, case["documents"])
            predictions.append({
                "case_id": case["case_id"], "raw_output": raw, "parsed": parsed,
                "json_valid": not any(e.startswith("invalid_json:") for e in errors),
                "schema_valid": not errors, "schema_errors": errors,
                "generation_seconds": elapsed, "generated_tokens": tokens,
                "input_documents": case["documents"],
            })
            count = len(parsed.get("items", [])) if isinstance(parsed, dict) and isinstance(parsed.get("items"), list) else 0
            print(f"{case['case_id']}: schema_valid={not errors} items={count} seconds={elapsed:.2f}")
        except Exception as exc:
            predictions.append({
                "case_id": case["case_id"], "raw_output": raw, "parsed": None,
                "json_valid": False, "schema_valid": False,
                "schema_errors": [f"generation_error: {type(exc).__name__}: {exc}"],
                "generation_seconds": elapsed, "generated_tokens": tokens,
                "input_documents": case["documents"],
            })
            print(f"{case['case_id']}: generation failed ({type(exc).__name__})")
    now = datetime.now(timezone.utc)
    run_id = now.strftime(f"{model_key}_%Y%m%dT%H%M%SZ")
    run_dir = root / "outputs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    metrics = score_predictions(cases, predictions)
    metadata = {
        **model.metadata(gpu_index), "run_id": run_id, "started_at_utc": now.isoformat(),
        "case_ids": [case["case_id"] for case in cases],
        "generation_max_new_tokens": max_new_tokens,
    }
    for name, payload in (("predictions.json", predictions), ("metrics.json", metrics), ("metadata.json", metadata)):
        (run_dir / name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8",
        )
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print(f"Saved synthetic-only outputs under {run_dir}")
    return run_dir
