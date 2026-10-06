import unittest
from chain_agents.summary.agent import invoke
from examples.support import sample,services

class BoundaryTests(unittest.TestCase):
    def test_scope_binding(self):
        r,s=sample();r['scope']=['other']
        with self.assertRaises(ValueError):invoke(r,s,services())
    def test_snapshot_binding(self):
        r,s=sample();r['input_snapshot_id']='wrong'
        with self.assertRaises(ValueError):invoke(r,s,services())
    def test_evaluation_time_required(self):
        r,s=sample();del r['evaluated_at']
        with self.assertRaises(ValueError):invoke(r,s,services())
