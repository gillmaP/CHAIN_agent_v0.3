import copy
import unittest

from chain_agents.summary.experiment import (
    parse_and_validate,
    score_predictions,
    synthetic_cases,
    validate_result,
)


class SummaryExperimentTests(unittest.TestCase):
    def setUp(self):
        self.case = synthetic_cases()[0]
        self.documents = self.case["documents"]

    def test_valid_schema_and_verbatim_quotes(self):
        result = {"summary": "환자는 왼쪽 팔 힘 저하를 호소했고 LKW는 12:55였습니다.",
                  "claims": copy.deepcopy(self.case["expected"])}
        self.assertEqual(validate_result(result, self.documents), [])

    def test_invalid_json_is_rejected(self):
        parsed, errors = parse_and_validate("not json", self.documents)
        self.assertIsNone(parsed)
        self.assertTrue(errors[0].startswith("invalid_json:"))

    def test_nonverbatim_quote_and_unknown_document_are_rejected(self):
        result = {"summary": "요약", "claims": [copy.deepcopy(self.case["expected"][0])]}
        result["claims"][0]["evidence"] = "환자는 팔이 약함"
        self.assertTrue(any("not present" in e for e in validate_result(result, self.documents)))
        result["claims"][0]["evidence"] = self.case["expected"][0]["evidence"]
        result["claims"][0]["source_document_id"] = "OTHER"
        self.assertTrue(any("source_document_id" in e for e in validate_result(result, self.documents)))

    def test_extra_fields_are_rejected(self):
        result = {"summary": "요약", "claims": [], "diagnosis": "stroke"}
        self.assertTrue(validate_result(result, self.documents))

    def test_gold_predictions_score_perfectly(self):
        prediction = {
            "case_id": self.case["case_id"], "json_valid": True, "schema_valid": True,
            "parsed": {"summary": "요약", "claims": copy.deepcopy(self.case["expected"])},
            "generation_seconds": 1.0,
        }
        metrics = score_predictions([self.case], [prediction])
        self.assertEqual(metrics["claim_precision"], 1.0)
        self.assertEqual(metrics["claim_recall"], 1.0)
        self.assertEqual(metrics["claim_f1"], 1.0)
        self.assertEqual(metrics["citation_support_rate"], 1.0)
        self.assertEqual(metrics["event_time_exact_rate"], 1.0)

    def test_note_entry_time_is_not_event_time(self):
        expected = self.case["expected"][1]
        self.assertNotEqual(expected["event_time"], self.documents[0]["documented_at"])
        self.assertEqual(expected["event_time"], "2026-10-06T13:40:00+09:00")


if __name__ == "__main__":
    unittest.main()
