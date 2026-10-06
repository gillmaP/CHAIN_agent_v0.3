import unittest
from chain_agents.summary.agent import invoke
from examples.support import sample,services
from chain_agents.common import canonical_hash

class SummaryTests(unittest.TestCase):
    def test_preserves_facts_and_provenance(self):
        r,s=sample();out=invoke(r,s,services())
        self.assertEqual(out['structured_context'],s['facts'])
        out['structured_context']['age']['source_ref']['version']=9
        self.assertEqual(s['facts']['age']['source_ref']['version'],1)
    def test_cache_reuse_and_changed_snapshot(self):
        r,s=sample();svc=services()
        self.assertFalse(invoke(r,s,svc)['cache']['hit']);r['request_id']='second'
        self.assertTrue(invoke(r,s,svc)['cache']['hit'])
        s['facts']['age']['value']=69;s['snapshot_id']=canonical_hash({k:v for k,v in s.items() if k!='snapshot_id'});r['input_snapshot_id']=s['snapshot_id']
        self.assertFalse(invoke(r,s,svc)['cache']['hit'])
    def test_false_zero_and_null_are_different(self):
        for value,expected in [(False,[]),(0,[]),(None,['age'])]:
            r,s=sample();s['facts']['age']['value']=value
            self.assertEqual(invoke(r,s,services())['missing_information'],expected)
    def test_conflict_error_and_retracted_are_missing(self):
        for status in ['CONFLICT','ERROR','RETRACTED','INVALIDATED']:
            r,s=sample();s['facts']['age']['status']=status
            self.assertEqual(invoke(r,s,services())['missing_information'],['age'])
