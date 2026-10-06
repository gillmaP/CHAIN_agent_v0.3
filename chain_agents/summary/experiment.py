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

MODEL_ID = "Qwen/Qwen3.5-9B"
MODEL_REVISION = "c202236235762e1c871ad0ccb60c8ee5ba337b9a"
PROMPT_VERSION = "clinical-summary-zero-shot-v1"
DATA_DEFAULT = "/data/data2/jhbak/CHAIN_agent_summary_prototype"
DATA_ROOTS = (Path("/data/data2"), Path("/data/data3"))
CONCEPTS = frozenset({
    "symptom.left_arm_weakness", "symptom.right_arm_weakness",
    "symptom.facial_droop", "symptom.dysarthria", "symptom.visual_change",
    "symptom.headache", "diagnosis.stroke", "time.symptom_onset",
    "time.last_known_well", "history.hypertension", "history.stroke",
    "medication.anticoagulant", "vital.blood_pressure", "lab.glucose",
})
FIELDS = frozenset({
    "subject", "concept", "value", "polarity", "temporality",
    "event_time", "source_document_id", "evidence",
})
SUBJECTS = {"patient", "family", "other", "unknown"}
POLARITIES = {"affirmed", "negated", "uncertain"}
TEMPORALITIES = {"current", "historical", "planned", "unknown"}


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


def _claim(subject, concept, value, polarity, temporality, event_time, doc_id, evidence):
    return {
        "subject": subject, "concept": concept, "value": value, "polarity": polarity,
        "temporality": temporality, "event_time": event_time,
        "source_document_id": doc_id, "evidence": evidence,
    }


def synthetic_cases():
    """Hand-authored notes; no patient files are read."""
    return [
        {
            "case_id": "ko_en_timing_negation",
            "documents": [_doc(
                "ER-001", "2026-10-06T14:12:00+09:00",
                "2026-10-06 14:12 응급실 기록. 마지막 정상 확인(last known well)은 12:55. "
                "오후 1시 40분부터 왼쪽 팔에 힘이 빠짐. facial droop와 dysarthria는 없다고 함.",
            )],
            "expected": [
                _claim("patient", "time.last_known_well", "12:55", "affirmed", "current", "2026-10-06T12:55:00+09:00", "ER-001", "마지막 정상 확인(last known well)은 12:55"),
                _claim("patient", "symptom.left_arm_weakness", "present", "affirmed", "current", "2026-10-06T13:40:00+09:00", "ER-001", "오후 1시 40분부터 왼쪽 팔에 힘이 빠짐"),
                _claim("patient", "symptom.facial_droop", "absent", "negated", "current", None, "ER-001", "facial droop와 dysarthria는 없다고 함"),
                _claim("patient", "symptom.dysarthria", "absent", "negated", "current", None, "ER-001", "facial droop와 dysarthria는 없다고 함"),
            ],
        },
        {
            "case_id": "uncertainty_person_history",
            "documents": [_doc(
                "NEURO-002", "2026-10-06T18:20:00+09:00",
                "2026-10-06 18:20 신경과 기록. Possible stroke, r/o ischemic event. "
                "말 어눌함(dysarthria)이 있는지는 환자도 확실히 모르겠다고 함. "
                "시야 이상은 없다고 보고함. 환자 과거력(PMH): hypertension. "
                "아버지는 70세에 stroke 병력이 있음. 환자는 현재 두통이 없다고 함.",
            )],
            "expected": [
                _claim("patient", "diagnosis.stroke", "possible", "uncertain", "current", None, "NEURO-002", "Possible stroke, r/o ischemic event"),
                _claim("patient", "symptom.dysarthria", "uncertain", "uncertain", "current", None, "NEURO-002", "말 어눌함(dysarthria)이 있는지는 환자도 확실히 모르겠다고 함"),
                _claim("patient", "symptom.visual_change", "absent", "negated", "current", None, "NEURO-002", "시야 이상은 없다고 보고함"),
                _claim("patient", "history.hypertension", "present", "affirmed", "historical", None, "NEURO-002", "환자 과거력(PMH): hypertension"),
                _claim("family", "history.stroke", "present", "affirmed", "historical", None, "NEURO-002", "아버지는 70세에 stroke 병력이 있음"),
                _claim("patient", "symptom.headache", "absent", "negated", "current", None, "NEURO-002", "환자는 현재 두통이 없다고 함"),
            ],
        },
        {
            "case_id": "medication_values_unknown_lkw",
            "documents": [_doc(
                "MEDS-003", "2026-10-06T19:30:00+09:00",
                "2026-10-06 19:30 약물 및 검사 확인. 현재 복용약: apixaban 5 mg twice daily. "
                "마지막 복용은 2026-10-05 22:00. BP 148/86 mmHg, random glucose 132 mg/dL. "
                "마지막 정상 시각(LKW)은 환자와 보호자가 알지 못해 확인 불가.",
            )],
            "expected": [
                _claim("patient", "medication.anticoagulant", "apixaban 5 mg twice daily", "affirmed", "current", "2026-10-05T22:00:00+09:00", "MEDS-003", "현재 복용약: apixaban 5 mg twice daily. 마지막 복용은 2026-10-05 22:00"),
                _claim("patient", "vital.blood_pressure", "148/86 mmHg", "affirmed", "current", None, "MEDS-003", "BP 148/86 mmHg"),
                _claim("patient", "lab.glucose", "132 mg/dL", "affirmed", "current", None, "MEDS-003", "random glucose 132 mg/dL"),
                _claim("patient", "time.last_known_well", None, "uncertain", "unknown", None, "MEDS-003", "마지막 정상 시각(LKW)은 환자와 보호자가 알지 못해 확인 불가"),
            ],
        },
        {
            "case_id": "conflicting_onset_times",
            "documents": [
                _doc("WITNESS-A", "2026-10-06T08:30:00+09:00",
                     "2026-10-06 08:30 보호자 기록: 가족은 증상 발생 시각을 오전 7시 55분이라고 기억함."),
                _doc("WITNESS-B", "2026-10-06T08:33:00+09:00",
                     "2026-10-06 08:33 구급대 기록: 동료는 증상 시작이 08:15였다고 목격 진술함."),
            ],
            "expected": [
                _claim("patient", "time.symptom_onset", "07:55", "affirmed", "current", "2026-10-06T07:55:00+09:00", "WITNESS-A", "증상 발생 시각을 오전 7시 55분이라고 기억함"),
                _claim("patient", "time.symptom_onset", "08:15", "affirmed", "current", "2026-10-06T08:15:00+09:00", "WITNESS-B", "증상 시작이 08:15였다고 목격 진술함"),
            ],
        },
    ]


SYSTEM_PROMPT = f"""You extract clinical information for a research prototype.
Use only the supplied synthetic notes. Do not diagnose, recommend treatment, calculate
eligibility, or infer undocumented facts.

Return one JSON object with exactly two keys: summary and claims. Write summary in
concise Korean and summarize only extracted claims. Preserve source disagreements and
uncertainty; do not turn uncertainty into a negative. Distinguish patient, family, other,
and unknown subjects. Separate historical from current findings.

documented_at is note-entry time, never an event time. event_time is null unless a
clinical event time is explicitly stated. Normalize explicit date/time to ISO-8601 with
the note's +09:00 timezone when possible. Never substitute note-entry time for onset or
LKW. Every claim needs an exact quote from its cited source. Preserve numbers, doses,
and units. Use null for unavailable value or event_time. An explicitly unknown LKW is a
time.last_known_well claim with null value/event_time, uncertain polarity, and unknown
temporality. Preserve conflicting source values as separate claims.

Allowed concepts: {", ".join(sorted(CONCEPTS))}
Allowed polarity: affirmed, negated, uncertain.
Allowed temporality: current, historical, planned, unknown.
Claim fields, exactly: subject, concept, value, polarity, temporality, event_time,
source_document_id, evidence. Return no markdown fences or extra fields."""


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


def _signature(claim):
    return (
        claim.get("subject"), claim.get("concept"), claim.get("polarity"),
        claim.get("temporality"), claim.get("event_time"), claim.get("source_document_id"),
    )


def _quote_supported(quote, text):
    return bool(quote.strip()) and _norm(quote) in _norm(text)


def validate_result(result, documents):
    errors = []
    if not isinstance(result, dict):
        return ["result must be a JSON object"]
    if set(result) != {"summary", "claims"}:
        errors.append("result must have exactly summary and claims")
    if not isinstance(result.get("summary"), str) or not result.get("summary", "").strip():
        errors.append("summary must be non-empty text")
    if not isinstance(result.get("claims"), list):
        return errors + ["claims must be a list"]
    docs = {doc["id"]: doc for doc in documents}
    for i, claim in enumerate(result["claims"]):
        where = f"claims[{i}]"
        if not isinstance(claim, dict):
            errors.append(f"{where} must be an object")
            continue
        if set(claim) != FIELDS:
            errors.append(f"{where} fields do not match schema")
            continue
        if claim["subject"] not in SUBJECTS:
            errors.append(f"{where}.subject invalid")
        if claim["concept"] not in CONCEPTS:
            errors.append(f"{where}.concept invalid")
        if claim["polarity"] not in POLARITIES:
            errors.append(f"{where}.polarity invalid")
        if claim["temporality"] not in TEMPORALITIES:
            errors.append(f"{where}.temporality invalid")
        value = claim["value"]
        if value is not None and (not isinstance(value, str) or not value.strip()):
            errors.append(f"{where}.value must be text or null")
        event_time = claim["event_time"]
        if event_time is not None:
            try:
                parsed_time = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
                if parsed_time.tzinfo is None:
                    errors.append(f"{where}.event_time must include an offset")
            except (ValueError, AttributeError):
                errors.append(f"{where}.event_time must be ISO-8601 or null")
        doc_id = claim["source_document_id"]
        if not isinstance(doc_id, str) or doc_id not in docs:
            errors.append(f"{where}.source_document_id is not in input")
        evidence = claim["evidence"]
        if not isinstance(evidence, str) or not evidence.strip():
            errors.append(f"{where}.evidence must be a quote")
        elif isinstance(doc_id, str) and doc_id in docs and not _quote_supported(evidence, docs[doc_id]["text"]):
            errors.append(f"{where}.evidence is not present in cited document")
    return errors


def parse_and_validate(raw, documents):
    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        return None, [f"invalid_json: {exc}"]
    return result, validate_result(result, documents)


def score_predictions(cases, predictions):
    by_case = {item["case_id"]: item for item in predictions}
    total = len(cases)
    json_valid = sum(bool(by_case.get(c["case_id"], {}).get("json_valid")) for c in cases)
    schema_valid = sum(bool(by_case.get(c["case_id"], {}).get("schema_valid")) for c in cases)
    gold, predicted = set(), set()
    gold_value, predicted_value = {}, {}
    gold_times, predicted_times = set(), set()
    claim_count = grounded = summaries = 0
    for case in cases:
        docs = {doc["id"]: doc for doc in case["documents"]}
        for claim in case["expected"]:
            key = _signature(claim)
            gold.add(key)
            gold_value[key] = _norm(claim.get("value"))
            if claim["concept"].startswith("time.") or claim.get("event_time") is not None:
                gold_times.add((claim["subject"], claim["concept"], claim.get("event_time"), claim["source_document_id"]))
        item = by_case.get(case["case_id"], {})
        result = item.get("parsed")
        if not item.get("schema_valid") or not isinstance(result, dict):
            continue
        summaries += bool(result.get("summary", "").strip())
        for claim in result.get("claims", []):
            claim_count += 1
            doc = docs.get(claim.get("source_document_id"))
            if doc and isinstance(claim.get("evidence"), str) and _quote_supported(claim["evidence"], doc["text"]):
                grounded += 1
            key = _signature(claim)
            predicted.add(key)
            predicted_value[key] = _norm(claim.get("value"))
            if claim.get("concept", "").startswith("time.") or claim.get("event_time") is not None:
                predicted_times.add((claim.get("subject"), claim.get("concept"), claim.get("event_time"), claim.get("source_document_id")))
    tp, fp, fn = len(gold & predicted), len(predicted - gold), len(gold - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    aligned = gold & predicted
    runtimes = [float(p["generation_seconds"]) for p in predictions if p.get("generation_seconds") is not None]
    return {
        "synthetic_dataset_version": "synthetic-stroke-summary-v1",
        "prompt_version": PROMPT_VERSION,
        "total_cases": total,
        "valid_json_rate": json_valid / total if total else 0.0,
        "valid_schema_rate": schema_valid / total if total else 0.0,
        "summary_present_rate": summaries / schema_valid if schema_valid else 0.0,
        "citation_support_rate": grounded / claim_count if claim_count else 0.0,
        "claim_precision": precision, "claim_recall": recall, "claim_f1": f1,
        "value_exact_rate_on_aligned_claims": (
            sum(gold_value[k] == predicted_value[k] for k in aligned) / len(aligned) if aligned else None
        ),
        "event_time_exact_rate": len(gold_times & predicted_times) / len(gold_times) if gold_times else None,
        "claims_scored": claim_count, "expected_claims": len(gold),
        "median_generation_seconds": statistics.median(runtimes) if runtimes else None,
    }


def download_model():
    root = experiment_root(create=True)
    os.environ["HF_HOME"] = str(root / "hf_cache")
    os.environ["HF_HUB_CACHE"] = str(root / "hf_cache" / "hub")
    from huggingface_hub import snapshot_download
    model_dir = root / "models" / "Qwen3.5-9B"
    snapshot_download(
        repo_id=MODEL_ID, revision=MODEL_REVISION,
        local_dir=str(model_dir), cache_dir=str(root / "hf_cache" / "hub"),
    )
    manifest = {
        "model_id": MODEL_ID, "revision": MODEL_REVISION, "license": "Apache-2.0",
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_directory": str(model_dir), "weights_stored_in_git": False,
    }
    (root / "model_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(f"Downloaded {MODEL_ID} at {MODEL_REVISION} to {model_dir}")


class LocalQwen:
    def __init__(self, model_dir, gpu_index="0", max_new_tokens=1800):
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_index)
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        from transformers import AutoModelForMultimodalLM, AutoProcessor
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; this experiment expects a local GPU.")
        self.torch, self.model_dir, self.max_new_tokens = torch, model_dir, max_new_tokens
        started = time.perf_counter()
        self.processor = AutoProcessor.from_pretrained(str(model_dir), local_files_only=True)
        self.model = AutoModelForMultimodalLM.from_pretrained(
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
        inputs = self.processor.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=True, return_dict=True,
            return_tensors="pt", enable_thinking=False,
        ).to(self.model.device)
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
            "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
            "model_path": str(self.model_dir), "prompt_version": PROMPT_VERSION,
            "transformers_version": __import__("transformers").__version__,
            "torch_version": self.torch.__version__, "cuda_runtime_version": self.torch.version.cuda,
            "gpu_index_requested": str(gpu_index), "gpu_name": gpu.name,
            "gpu_total_memory_bytes": gpu.total_memory, "model_load_seconds": self.load_seconds,
            "offline_inference": True, "synthetic_only": True,
        }


def run_experiment(gpu_index="0", max_new_tokens=1800, case_limit=None):
    root = experiment_root(create=True)
    model_dir = root / "models" / "Qwen3.5-9B"
    if not (model_dir / "config.json").is_file():
        raise FileNotFoundError(f"Missing model at {model_dir}; run the download command first.")
    cases = synthetic_cases()
    if case_limit is not None:
        if case_limit < 1:
            raise ValueError("case_limit must be at least 1")
        cases = cases[:case_limit]
    model = LocalQwen(model_dir, gpu_index, max_new_tokens)
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
            count = len(parsed.get("claims", [])) if isinstance(parsed, dict) and isinstance(parsed.get("claims"), list) else 0
            print(f"{case['case_id']}: schema_valid={not errors} claims={count} seconds={elapsed:.2f}")
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
    run_id = now.strftime("qwen35_9b_%Y%m%dT%H%M%SZ")
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
