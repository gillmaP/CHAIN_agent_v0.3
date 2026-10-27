"""Run in a generated reference checkout; standalone Agent CI skips these tests."""
import copy
import importlib.util
import unittest
from types import SimpleNamespace

HOST_AVAILABLE = importlib.util.find_spec('chain_demo') is not None
if HOST_AVAILABLE:
    from chain_demo.orchestration_config import load_orchestration_bundle
    from chain_demo.data_io import load_initial
    from chain_demo.contracts import validate_hitl_request
    from chain_demo.agents.runtime import AgentRuntime
    from chain_agents.tpa.orchestrator import EvidenceFirstEngine, CHECKPOINT
    from chain_agents.tpa.demo import sample
    from chain_agents.tpa.agent import invoke


@unittest.skipUnless(HOST_AVAILABLE,'Requires the generated pinned reference Host')
class HostTests(unittest.TestCase):
    def engine(self, *, missing=False, mismatch=False):
        config = load_orchestration_bundle()
        initial = load_initial('episodes/stroke_reference_001_v03/initial.json')
        request, snapshot = sample()
        now = request['evaluated_at']
        engine = EvidenceFirstEngine(config['engine'],initial,now=now)
        # Checkpoint unit fixture: earlier State/CT Event routing is exercised by the full demo.
        engine.context._facts.update(copy.deepcopy(snapshot['facts']))
        engine.context._known_at = now
        if missing:
            engine.context._facts['inr'].update(value=None,status='PENDING')
        if mismatch:
            engine.context._facts['ncct_order_id']['value']='OTHER-ORDER'
        engine._enter('S2_1',{})
        return engine

    def test_ct_opens_hitl_before_agent_completion(self):
        engine = self.engine(missing=True)
        review = engine.open_hitl[CHECKPOINT]
        self.assertEqual(review['status'],'OPEN')
        self.assertEqual(review['results'],[])
        self.assertEqual(review['request']['evidence_mode'],'SOURCE_SNAPSHOT')
        self.assertEqual(review['snapshot']['facts']['inr']['status'],'PENDING')
        validate_hitl_request(review['request'],review['snapshot'],review['results'])

    def test_registered_runtime_returns_v2_domain_result(self):
        engine = self.engine(missing=True)
        command = next(c for c in engine.pending.values() if c.get('alias')=='tpa_decision_support')
        reply = AgentRuntime(load_orchestration_bundle()['agents']).invoke(command['job'])
        self.assertEqual(reply['status'],'SUCCESS')
        self.assertEqual(reply['result']['assessment']['schema'],'chain-tpa-assessment/prototype-v2')
        self.assertEqual(reply['result']['evidence_package']['inr']['status'],'PENDING')

    def test_wrong_ct_order_cannot_open(self):
        self.assertNotIn(CHECKPOINT,self.engine(mismatch=True).open_hitl)

    def test_late_success_requires_explicit_new_review(self):
        engine = self.engine()
        old = engine.open_hitl[CHECKPOINT]
        before = copy.deepcopy(old)
        command = next(c for c in engine.pending.values() if c.get('alias')=='tpa_decision_support')
        request, snapshot = command['job']['request'], command['job']['snapshot']
        reply = {'contract_schema':'chain-agent-result/v0.3',
                 **{k:request[k] for k in ('request_id','agent_id','agent_version','manifest_hash','input_snapshot_id')},
                 'status':'SUCCESS','result':invoke(request,snapshot,SimpleNamespace()),
                 'evidence':copy.deepcopy(request['dependencies']),'produced_time':request['evaluated_at']}
        engine.complete(command['id'],reply,engine.now)
        self.assertEqual(old,before)
        engine.refresh_tpa_review({'contract_schema':'chain-hitl-resume/v0.3','command_id':'FRESH-RESULT',
            'prior_request_id':old['request']['request_id'],'actor':{'role':'NEUROLOGIST','staff_id':'SYNTHETIC'},
            'requested_at':engine.now},engine.now)
        new = engine.open_hitl[CHECKPOINT]
        self.assertNotEqual(old['request']['request_id'],new['request']['request_id'])
        self.assertEqual(new['results'][0]['request_id'],command['id'])
        validate_hitl_request(new['request'],new['snapshot'],new['results'])

    def test_source_only_mode_cannot_bypass_ct_or_other_checkpoints(self):
        engine = self.engine()
        review = copy.deepcopy(engine.open_hitl[CHECKPOINT])
        review['request']['checkpoint'] = 'HITL_1_PROCEED_TO_CT'
        with self.assertRaises(ValueError):
            validate_hitl_request(review['request'],review['snapshot'],[])

    def test_previous_history_mode_keeps_legacy_wait(self):
        engine = self.engine()
        engine.evidence_first_enabled=False
        engine.open_hitl.clear()
        engine._consume({'kind':'hitl','checkpoint':CHECKPOINT,'generation':engine.generation})
        self.assertNotIn(CHECKPOINT,engine.open_hitl)

    def test_failure_does_not_close_or_rewrite_review(self):
        for error in ('AGENT_INVALID_OUTPUT','TimeoutError'):
            engine = self.engine()
            before = copy.deepcopy(engine.open_hitl[CHECKPOINT])
            command = next(c for c in engine.pending.values() if c.get('alias')=='tpa_decision_support')
            engine.complete(command['id'],{'error':error},engine.now)
            self.assertEqual(engine.open_hitl[CHECKPOINT],before)
            self.assertEqual(engine.snapshot()['tpa_execution']['final']['status'],'FAILED')

    def test_unauthorized_decision_stays_rejected(self):
        engine = self.engine()
        r = engine.open_hitl[CHECKPOINT]['request']
        decision = {'contract_schema':'chain-hitl-decision/v0.3','request_id':r['request_id'],
            'evidence_snapshot_id':r['evidence_snapshot_id'],'decision':'THROMBOLYSIS_YES',
            'actor':{'role':'UNAUTHORIZED','staff_id':'SYNTHETIC'},'confirmed_items':[],
            'evidence_viewed':[r['evidence_snapshot_id']],'comment':'synthetic test','recorded_at':engine.now}
        engine.decide(decision,engine.now)
        self.assertEqual(engine.state,'S2_1')

    def test_new_source_creates_new_request_without_mutating_old_bundle(self):
        engine = self.engine()
        old = engine.open_hitl[CHECKPOINT]
        before = copy.deepcopy(old['snapshot'])
        engine.context._facts['inr']['value']=1.2
        engine.context._facts['inr']['source_ref']['version']=2
        engine._consume({'kind':'hitl','checkpoint':CHECKPOINT,'generation':engine.generation})
        self.assertEqual(old['status'],'INVALIDATED')
        self.assertEqual(old['snapshot'],before)
        self.assertNotEqual(old['request']['request_id'],engine.open_hitl[CHECKPOINT]['request']['request_id'])

    def test_refresh_is_idempotent_and_role_checked(self):
        engine = self.engine()
        prior = engine.open_hitl[CHECKPOINT]['request']['request_id']
        request = {'contract_schema':'chain-hitl-resume/v0.3','command_id':'REFRESH-1','prior_request_id':prior,
                   'actor':{'role':'NEUROLOGIST','staff_id':'SYNTHETIC'},'requested_at':engine.now}
        engine.refresh_tpa_review(request,engine.now)
        current = engine.open_hitl[CHECKPOINT]['request']['request_id']
        self.assertNotEqual(prior,current)
        engine.refresh_tpa_review(request,engine.now)
        self.assertEqual(engine.open_hitl[CHECKPOINT]['request']['request_id'],current)

    def test_existing_confirmation_requirements_still_apply(self):
        engine = self.engine()
        r = engine.open_hitl[CHECKPOINT]['request']
        decision = {'contract_schema':'chain-hitl-decision/v0.3','request_id':r['request_id'],
            'evidence_snapshot_id':r['evidence_snapshot_id'],'decision':'THROMBOLYSIS_YES',
            'actor':{'role':'NEUROLOGIST','staff_id':'SYNTHETIC'},'confirmed_items':[],
            'evidence_viewed':[r['evidence_snapshot_id']],'comment':'synthetic test','recorded_at':engine.now}
        engine.decide(decision,engine.now)
        self.assertEqual(engine.state,'S2_1')


if __name__ == '__main__':
    unittest.main()
