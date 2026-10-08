import copy
import unittest
from .history_s1_contract import QUESTION_ORDER, finalize_facts, validate_model_payload
from .history_s1_cases import cases
from .history_s1_experiment import GPU_ASSIGNMENTS
from .history_s1_extractor import DIRECT_PROMPT, EVIDENCE_FIRST_PROMPT

class ReviewedStatusTests(unittest.TestCase):
    def setUp(self):
        self.ref = 'document:unit'
        self.docs = {self.ref: {'text': '병력은 문진하지 않았다. 병력이 없다. 복용하지 않는다. 복용한다.'}}

    def payload(self, facts):
        return {'facts': facts, 'reviewed_documents': [self.ref]}

    def fact(self, q, status, value, quote=None):
        return {'question': q, 'status': status, 'value': value,
                'evidence': [{'source_ref': self.ref, 'quote': quote}] if quote else []}

    def test_nonassessment_gold_consistent(self):
        data = {c['case_id']: c for c in cases()}
        for cid, q in [('03_family_current', 'previous_stroke'), ('06_partial_negation', 'recent_bleeding')]:
            item = next(x for x in data[cid]['gold_items'] if x['question'] == q)
            self.assertEqual(item['status'], 'explicitly_unknown')
            self.assertIsNone(item['value'])
            self.assertTrue(item['evidence'])

    def test_not_stated_with_full_keys_accepted_for_every_question(self):
        for q in QUESTION_ORDER:
            payload = self.payload([self.fact(q, 'not_stated', None)])
            validate_model_payload(payload, self.docs, [q])
            self.assertEqual(finalize_facts(payload, self.docs, [q])[0]['status'], 'not_stated')

    def test_no_mention_never_overrides_explicit_unknown_or_documented_false(self):
        q = 'previous_stroke'
        for status, value, quote in [('explicitly_unknown', None, '병력은 문진하지 않았다.'),
                                     ('documented', False, '병력이 없다.')]:
            payload = self.payload([self.fact(q, 'not_stated', None), self.fact(q, status, value, quote)])
            original = copy.deepcopy(payload)
            result = finalize_facts(payload, self.docs, [q])[0]
            self.assertEqual(result['status'], status)
            self.assertIs(result['value'], value)
            self.assertEqual(payload, original)

    def test_unknown_with_false_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_model_payload(self.payload([self.fact('previous_stroke', 'explicitly_unknown', False, '병력은 문진하지 않았다.')]), self.docs, ['previous_stroke'])

    def test_missing_keys_still_rejected_with_actionable_message(self):
        with self.assertRaisesRegex(ValueError, 'missing=.*evidence.*value'):
            validate_model_payload(self.payload([{'question': 'previous_stroke', 'status': 'not_stated'}]), self.docs, ['previous_stroke'])

    def test_nonverbatim_quote_still_rejected(self):
        with self.assertRaises(ValueError):
            validate_model_payload(self.payload([self.fact('previous_stroke', 'documented', False, '뇌졸중 병력이 없다.')]), self.docs, ['previous_stroke'])

    def test_conflicts_survive_no_mention_marker(self):
        q = 'anticoagulant_use'
        result = finalize_facts(self.payload([self.fact(q, 'not_stated', None),
            self.fact(q, 'documented', False, '복용하지 않는다.'), self.fact(q, 'documented', True, '복용한다.')]), self.docs, [q])[0]
        self.assertEqual(result['status'], 'conflicting')
        self.assertEqual({a['value'] for a in result['alternatives']}, {True, False})

    def test_controlled_order_and_separate_gpus(self):
        self.assertEqual(EVIDENCE_FIRST_PROMPT.replace('Each fact has EXACTLY question, evidence, status, value.',
            'Each fact has EXACTLY question, status, value, evidence.'), DIRECT_PROMPT)
        self.assertEqual(GPU_ASSIGNMENTS, {'qwen35_9b': '2', 'gemma4_12b_it': '3'})

if __name__ == '__main__':
    unittest.main()
