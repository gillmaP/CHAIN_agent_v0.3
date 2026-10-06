import copy
import unittest
from chain_agents.screening.agent import invoke
from examples.support import sample,services,SyntheticBackend

class ScreeningTests(unittest.TestCase):
    def test_requires_explicit_backend(self):
        r,s=sample('screening')
        with self.assertRaises(ValueError):invoke(r,s,services())
    def test_positive_and_negative_fixture_without_input_mutation(self):
        for outcome in ['POSITIVE','NEGATIVE']:
            r,s=sample('screening');before=copy.deepcopy((r,s))
            expected={'screening_result':outcome,'mock_only':True,'basis':['EXPLICIT_TEST']}
            self.assertEqual(invoke(r,s,services(SyntheticBackend(r,s,expected))),expected)
            self.assertEqual((r,s),before)
    def test_wrong_fixture_input_rejected(self):
        r,s=sample('screening');b=SyntheticBackend(r,s,{})
        r['request_id']='different'
        with self.assertRaises(ValueError):invoke(r,s,services(b))
    def test_invalid_domain_output_rejected(self):
        r,s=sample('screening')
        for out in [{'error':'failed'}, {'screening_result':'POSITIVE','mock_only':False,'basis':['test']}]:
            with self.assertRaises(ValueError):invoke(r,s,services(SyntheticBackend(r,s,out)))
