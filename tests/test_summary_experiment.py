import copy
import json
import unittest

def json_text(value):
    return json.dumps(value, ensure_ascii=False)


from chain_agents.summary.experiment import (
    MODELS,
    parse_and_validate,
    score_predictions,
    synthetic_cases,
    validate_result,
)


class SummaryExperimentTests(unittest.TestCase):
    def setUp(self):
        self.case = synthetic_cases()[0]
        self.documents = self.case["documents"]

    def test_model_candidates_have_pinned_revisions(self):
        self.assertEqual(set(MODELS), {"qwen35_9b", "qwen25_14b_instruct", "gemma4_12b_it", "medgemma15_4b_it"})
        for model in MODELS.values():
            self.assertEqual(len(model["revision"]), 40)
            self.assertTrue(model["repo_id"])
            self.assertTrue(model["license"])

    def test_valid_schema_and_verbatim_quotes(self):
        result = {"summary": "환자는 왼쪽 팔 힘 저하를 호소했고 LKW는 12:55였습니다.",
                  "items": copy.deepcopy(self.case["expected"])}
        self.assertEqual(validate_result(result, self.documents), [])

    def test_absent_finding_is_status_and_has_no_null_value(self):
        absent = copy.deepcopy(self.case["expected"][2])
        self.assertEqual(absent["status"], "absent")
        self.assertNotIn("value", absent)
        self.assertNotIn("polarity", absent)

    def test_recorded_state_is_reserved_for_timeline_and_measurements(self):
        history = copy.deepcopy(synthetic_cases()[1]["expected"][3])
        history["status"] = "recorded"
        self.assertTrue(any("only for timeline" in e for e in validate_result(
            {"summary": "요약", "items": [history]}, synthetic_cases()[1]["documents"]
        )))

    def test_reporter_accuracy_is_separate_from_core_fact_f1(self):
        prediction = {
            "case_id": self.case["case_id"], "json_valid": True, "schema_valid": True,
            "parsed": {"summary": "요약", "items": copy.deepcopy(self.case["expected"])},
            "generation_seconds": 1.0,
        }
        prediction["parsed"]["items"][0]["reported_by"] = "clinician"
        metrics = score_predictions([self.case], [prediction])
        self.assertEqual(metrics["fact_f1"], 1.0)
        self.assertEqual(metrics["reporter_accuracy_on_aligned_facts"], 0.75)

    def test_event_time_and_note_entry_time_are_separate(self):
        onset = self.case["expected"][1]
        self.assertEqual(onset["event_time"], "2026-10-06T13:40:00+09:00")
        self.assertEqual(onset["source"]["documented_at"], "2026-10-06T14:12:00+09:00")
        self.assertNotEqual(onset["event_time"], onset["source"]["documented_at"])

    def test_wrong_source_time_is_rejected(self):
        result = {"summary": "요약", "items": [copy.deepcopy(self.case["expected"][0])]}
        result["items"][0]["source"]["documented_at"] = "2026-10-06T12:55:00+09:00"
        self.assertTrue(any("documented_at" in e for e in validate_result(result, self.documents)))

    def test_omitted_reporter_defaults_to_not_stated(self):
        item = copy.deepcopy(self.case["expected"][0])
        item.pop("reported_by")
        parsed, errors = parse_and_validate(json_text({"summary": "요약", "items": [item]}), self.documents)
        self.assertEqual(errors, [])
        self.assertEqual(parsed["items"][0]["reported_by"], "not_stated")

    def test_invalid_json_is_rejected(self):
        parsed, errors = parse_and_validate("not json", self.documents)
        self.assertIsNone(parsed)
        self.assertTrue(errors[0].startswith("invalid_json:"))

    def test_nonverbatim_quote_and_unknown_document_are_rejected(self):
        result = {"summary": "요약", "items": [copy.deepcopy(self.case["expected"][0])]}
        result["items"][0]["source"]["quote"] = "환자는 팔이 약함"
        self.assertTrue(any("not present" in e for e in validate_result(result, self.documents)))
        result["items"][0]["source"]["quote"] = self.case["expected"][0]["source"]["quote"]
        result["items"][0]["source"]["document_id"] = "OTHER"
        self.assertTrue(any("document_id" in e for e in validate_result(result, self.documents)))

    def test_extra_fields_and_null_values_are_rejected(self):
        result = {"summary": "요약", "items": copy.deepcopy(self.case["expected"])}
        result["extra"] = "unsupported"
        self.assertTrue(validate_result(result, self.documents))
        result.pop("extra")
        result["items"][2]["value"] = None
        self.assertTrue(any("value" in e for e in validate_result(result, self.documents)))

    def test_gold_predictions_score_perfectly(self):
        prediction = {
            "case_id": self.case["case_id"], "json_valid": True, "schema_valid": True,
            "parsed": {"summary": "요약", "items": copy.deepcopy(self.case["expected"])},
            "generation_seconds": 1.0,
        }
        metrics = score_predictions([self.case], [prediction])
        self.assertEqual(metrics["fact_precision"], 1.0)
        self.assertEqual(metrics["fact_recall"], 1.0)
        self.assertEqual(metrics["fact_f1"], 1.0)
        self.assertEqual(metrics["quote_support_rate"], 1.0)
        self.assertEqual(metrics["time_fact_exact_rate"], 1.0)
        self.assertEqual(metrics["reporter_accuracy_on_aligned_facts"], 1.0)

    def test_conflicting_reporters_remain_distinct(self):
        case = synthetic_cases()[3]
        first, second = case["expected"]
        self.assertEqual(first["subject"], second["subject"])
        self.assertNotEqual(first["reported_by"], second["reported_by"])
        self.assertNotEqual(first["event_time"], second["event_time"])
        self.assertNotEqual(first["source"]["document_id"], second["source"]["document_id"])


if __name__ == "__main__":
    unittest.main()
