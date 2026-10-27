import copy
import unittest
from types import SimpleNamespace
from chain_agents.common import canonical_hash
from chain_agents.tpa.agent import invoke
from chain_agents.tpa.demo import sample
from chain_agents.tpa.manual import weight_facts, weight_preview
from chain_agents.tpa.policy import Policy
from chain_agents.tpa.summary_adapter import summary_facts, merge_summary


def bind(request, snapshot):
    snapshot['snapshot_id'] = canonical_hash({k:v for k,v in snapshot.items() if k != 'snapshot_id'})
    request.update(input_snapshot_id=snapshot['snapshot_id'],scope=list(snapshot['facts']),
                   dependencies=[f['source_ref'] for f in snapshot['facts'].values()])


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.request, self.snapshot = sample()

    def output(self, services=None):
        bind(self.request,self.snapshot)
        return invoke(self.request,self.snapshot,services or SimpleNamespace())

    def test_output_contract_and_input_preservation(self):
        bind(self.request,self.snapshot)
        before = copy.deepcopy((self.request,self.snapshot))
        result = self.output()
        self.assertEqual(set(result),{'mode','evidence_package','assessment','mock_only'})
        self.assertEqual(result['assessment']['schema'],'chain-tpa-assessment/prototype-v2')
        self.assertEqual(result['evidence_package'],self.snapshot['facts'])
        self.assertEqual(before,(self.request,self.snapshot))
        self.assertTrue(result['mock_only'])

    def test_remaining_time_uses_explicit_evaluation(self):
        self.assertEqual(self.output()['assessment']['time_window']['remaining_seconds'],8940)

    def test_summary_point_and_uncertain_times(self):
        for kind in ('point','approximate','interval','before','after','partial'):
            with self.subTest(kind=kind):
                self.snapshot['facts']['lkw']['value'] = {'kind':kind,'start':'2026-10-06T13:35:00+09:00',
                    'end':None,'precision':'minute','original_text':'합성 시간 기록'}
                value = self.snapshot['facts']['lkw']['value']
                if kind == 'before':
                    value['start'],value['end'] = None,value['start']
                elif kind == 'interval':
                    value['end'] = '2026-10-06T13:40:00+09:00'
                elif kind == 'partial':
                    value['start'],value['precision'] = '2026-10-06','day'
                result = self.output()['assessment']['time_window']
                self.assertEqual(result['remaining_seconds'],8940 if kind=='point' else None)

    def test_missing_lkw_has_no_fabricated_deadline(self):
        self.snapshot['facts']['lkw'].update(value=None,status='UNKNOWN')
        window = self.output()['assessment']['time_window']
        self.assertIsNone(window['deadline'])
        self.assertIsNone(window['remaining_seconds'])

    def test_expired_standard_window_is_not_overall_ineligible(self):
        self.snapshot['facts']['lkw']['value'] = '2026-10-06T10:00:00+09:00'
        result = self.output()['assessment']
        self.assertEqual(result['time_window']['remaining_seconds'],0)
        self.assertEqual(result['status'],'PHYSICIAN_REVIEW_REQUIRED')

    def test_protocol_is_deployment_owned_and_validated(self):
        for configuration in ({'unknown':1},{'sbp_limit':True},{'inr_max':float('nan')},
                              {'approval_status':'SITE_APPROVED'}):
            with self.subTest(configuration=configuration),self.assertRaises(ValueError):
                self.output(SimpleNamespace(ivt_protocol=configuration))

    def test_site_protocol_is_identified_and_changes_threshold(self):
        policy = Policy(protocol_id='SYNTHETIC-SITE-PROTOCOL',site_id='SYNTHETIC',approved_by='SYNTHETIC-REVIEW',
                        approval_status='SITE_APPROVED',sbp_limit=170)
        assessment = self.output(SimpleNamespace(ivt_protocol=policy))['assessment']
        self.assertEqual(assessment['protocol']['protocol_id'],policy.protocol_id)
        bp = next(c for c in assessment['checks'] if c['check_id']=='C06_BP_LT_185_110')
        self.assertEqual(bp['clinical_result'],'REVIEW_REQUIRED')

    def test_research_failure_is_not_a_site_contraindication(self):
        self.snapshot['facts']['platelet_count']['value'] = 60000
        check = self.output()['assessment']['checks'][2]
        self.assertEqual(check['result'],'FAIL')
        self.assertEqual(check['clinical_result'],'REVIEW_REQUIRED')
        self.assertEqual(check['data_status'],'AVAILABLE')

    def test_data_and_clinical_states_are_independent(self):
        self.snapshot['facts']['inr'].update(value=None,status='PENDING')
        check = self.output()['assessment']['checks'][3]
        self.assertEqual((check['data_status'],check['clinical_result']),('PENDING','NOT_ASSESSED'))

    def test_no_record_is_not_a_confirmed_negative(self):
        self.snapshot['facts']['anticoagulant'].update(value=None,status='NO_EVIDENCE')
        check = self.output()['assessment']['checks'][4]
        self.assertEqual(check['data_status'],'NO_RECORD')
        self.assertNotEqual(check['clinical_result'],'CONDITION_NOT_MET')

    def test_multiple_glucose_sources_are_not_overwritten(self):
        for name,value in (('glucose_poct',49),('glucose_lab',121)):
            fact = copy.deepcopy(self.snapshot['facts']['glucose'])
            fact['value']=value
            fact['source_ref']['field']=name
            self.snapshot['facts'][name]=fact
        result = self.output()
        check = next(c for c in result['assessment']['checks'] if c['check_id']=='C07_GLUCOSE_50_400')
        self.assertEqual([v['mg_dl'] for v in check['value']['observations']],[49,121])
        self.assertEqual(check['clinical_result'],'REVIEW_REQUIRED')
        self.assertEqual(result['evidence_package'],self.snapshot['facts'])

    def test_optional_aptt_and_readings_remain_reviewable(self):
        for name,value in (('aptt',35),('a04_hemorrhage',False),('physician_ncct_read',False)):
            fact = copy.deepcopy(self.snapshot['facts']['inr'])
            fact.update(value=value,unit='s' if name=='aptt' else None)
            fact['source_ref']['field']=name
            self.snapshot['facts'][name]=fact
        checks = self.output()['assessment']['checks']
        self.assertEqual(len(checks),15)
        self.assertTrue(all(c['clinical_result']=='REVIEW_REQUIRED' for c in checks[12:]))

    def test_weight_is_never_silently_called_measured(self):
        self.assertEqual(self.output()['assessment']['dose_preview']['weight_method'],'UNKNOWN')
        for method in ('MEASURED','PATIENT_REPORTED','CAREGIVER_REPORTED','ESTIMATED'):
            result = weight_preview(67,method=method,staff_id='SYNTHETIC',entry_id='ENTRY-1',version=1,
                                    recorded_at=self.request['evaluated_at'])
            self.assertEqual(result['weight_method'],method)
            self.assertEqual(result['options'][0]['total_mg'],60.3)
            self.assertFalse(result['auto_order'])

    def test_bad_weight_entry_is_rejected(self):
        for weight in (True,0,-1,float('inf'),'67'):
            with self.subTest(weight=weight),self.assertRaises(ValueError):
                weight_facts(weight,method='MEASURED',staff_id='SYNTHETIC',entry_id='E1',version=1,
                             recorded_at=self.request['evaluated_at'])

    def test_summary_mapping_preserves_unknown_and_quotes(self):
        summary = {'schema_version':'summary-items/v1','episode_id':'EP','encounter_id':'ENC',
            'items':[{'question':'anticoagulant_use','status':'not_stated','value':None,'evidence':[],'alternatives':[]}]}
        before = copy.deepcopy(summary)
        mapped = summary_facts(summary,episode_id='EP',encounter_id='ENC',
            source_ref={'system':'A02','record_id':'SUM-1','version':1},
            source_time=self.request['evaluated_at'],known_at=self.request['evaluated_at'])
        self.assertEqual(mapped['anticoagulant']['status'],'NO_EVIDENCE')
        self.assertIsNone(mapped['anticoagulant']['value'])
        self.assertEqual(mapped['summary_evidence']['value'],summary['items'])
        self.assertEqual(summary,before)
        with self.assertRaises(ValueError):
            summary_facts(summary,episode_id='WRONG',encounter_id='ENC',source_ref={},source_time='',known_at='')

    def test_summary_conflict_preserves_both_candidates(self):
        fact = copy.deepcopy(self.snapshot['facts']['inr'])
        fact.update(value=1.8)
        fact['source_ref']['version']=2
        result = merge_summary(self.snapshot,{'inr':fact})
        self.assertEqual(result['facts']['inr']['status'],'CONFLICT')
        self.assertEqual([f['value'] for f in result['facts']['inr_alternatives']['value']],[1.04,1.8])
        self.assertEqual(self.snapshot['facts']['inr']['value'],1.04)

    def test_equivalent_summary_time_is_not_a_conflict(self):
        incoming = copy.deepcopy(self.snapshot['facts']['lkw'])
        incoming['value'] = {'kind':'point','start':incoming['value'],'end':None,
                             'precision':'minute','original_text':'합성 시간'}
        merged = merge_summary(self.snapshot,{'lkw':incoming})
        self.assertEqual(merged['facts']['lkw'],self.snapshot['facts']['lkw'])

    def test_malformed_summary_time_is_rejected(self):
        self.snapshot['facts']['lkw']['value'] = {'kind':'interval','start':'2026-10-06T13:35:00+09:00',
            'end':None,'precision':'minute','original_text':'합성 시간'}
        with self.assertRaises(ValueError):
            self.output()


if __name__ == '__main__':
    unittest.main()
