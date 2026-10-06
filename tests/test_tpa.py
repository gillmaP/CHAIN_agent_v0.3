import unittest
from chain_agents.tpa.agent import invoke
from examples.support import sample,services

class TpaTests(unittest.TestCase):
    def test_modes_and_exact_domain_keys(self):
        for mode in ['interim','final']:
            r,s=sample(mode);out=invoke(r,s,services())
            self.assertEqual(set(out),{'mode','evidence_package','assessment','mock_only'})
            self.assertEqual(out['mode'],mode);self.assertTrue(out['mock_only'])
            self.assertEqual(out['evidence_package'],s['facts'])
    def test_missing_input_is_pending(self):
        r,s=sample('final');s['facts']['age']['value']=None
        self.assertEqual(invoke(r,s,services())['assessment'],'PENDING_MOCK')
    def test_available_never_means_eligible(self):
        r,s=sample('final');out=invoke(r,s,services())
        self.assertEqual(out['assessment'],'STRUCTURED_MOCK_ONLY')
        self.assertNotIn('dose_suggestion',out)
    def test_wrong_mode_fails(self):
        r,s=sample('context')
        with self.assertRaises(ValueError):invoke(r,s,services())
