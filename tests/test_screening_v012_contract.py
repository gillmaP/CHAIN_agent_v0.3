"""Mock v0.12 reference case I/O contract tests; no GPU or HTTP listener needed."""
import copy
import json
from pathlib import Path
import unittest

from chain_agents.screening.agent import invoke_v012
from chain_agents.screening.v012_contract import (
    INPUT_FIELDS, OUTPUT_FIELDS, V012ContractError, validate_v012_input,
    validate_v012_output,
)
from chain_agents.screening.site_data_api import SyntheticFixtureDataAPI, HttpSiteDataAPI

ROOT = Path(__file__).resolve().parents[1]

def _json(name):
    return json.loads((ROOT/'examples'/name).read_text(encoding='utf-8'))

class _SyntheticModel:
    model_key = 'synthetic-unittest-not-LLM'
    model_revision = 'none'
    def generate(self, messages):
        obj = json.loads(messages[1]['content'])
        a = obj['documents'][0]['source_ref']
        b = obj['documents'][1]['source_ref']
        return json.dumps({'findings': [
            {'code':'acute_onset','status':'present','source_ref':a,
             'quote':'13:35경 딸과 전화통화 시까지 특이증상 없었다고 함'},
            {'code':'lkw','status':'present','source_ref':a,
             'quote':'13:35경 딸과 전화통화 시까지 특이증상 없었다고 함'},
            {'code':'focal_weakness','status':'present','source_ref':a,
             'quote':'Motor: Rt. U/E G2, Rt. L/E G3, Lt. side G5'},
            {'code':'fast_positive','status':'present','source_ref':b,
             'quote':'FAST: Face(+) Arm(+) Speech(+)'},
        ]}, ensure_ascii=False)

class _InvalidModel:
    model_key = 'malformed-model'
    model_revision = 'none'
    def generate(self, messages):
        return 'NOT_JSON'


class MockV012ContractTest(unittest.TestCase):
    def setUp(self):
        self.input = _json('v012_screening_request.json')
        self.data = _json('v012_screening_site_data_fixture.json')
        self.ref_output = _json('v012_screening_reference_output.json')

    def _call(self, req=None, data=None, model=None):
        return invoke_v012(req if req is not None else self.input,
                           execution_id='EXE-HYG-261006-0141',
                           data_api=SyntheticFixtureDataAPI(data if data is not None else self.data),
                           model=model if model is not None else _SyntheticModel(),
                           produced_time='2026-10-06T15:20:04+09:00')

    def test_official_input_shape_exact(self):
        self.assertEqual(set(self.input), INPUT_FIELDS)
        self.assertEqual(set(validate_v012_input(self.input)), INPUT_FIELDS)
        self.assertEqual(self.input['input_references'], [
            'document:DOC-2610060412@1','document:DOC-2610060403@2',
            'encounter:E261006058','observation:vital_signs',
            'observation:poct_glucose','condition:problem_list'])

    def test_official_output_top_level_and_nested_field_sets(self):
        actual = self._call()
        expected = self.ref_output
        self.assertEqual(set(actual), OUTPUT_FIELDS)
        self.assertEqual(set(actual), set(expected))
        for name in ('result','clinical_times'):
            self.assertEqual(set(actual[name]), set(expected[name]), name)
        for name in ('rule_trace','text_derived_findings','evidence'):
            self.assertTrue(actual[name])
            self.assertEqual(set(actual[name][0]), set(expected[name][0]), name)
        self.assertTrue(set(expected['model_info']).issubset(actual['model_info']))
        self.assertEqual(actual['result']['screening_result'],'POSITIVE')
        self.assertEqual(actual['result']['proposed_state'],'S1')
        self.assertEqual(actual['clinical_times']['last_known_well'], '2026-10-06T13:35:00+09:00')
        self.assertEqual(actual['produced_time'], '2026-10-06T15:20:04+09:00')
        validate_v012_output(actual)

    def test_reject_missing_or_unknown_top_level_field(self):
        payload = copy.deepcopy(self.input)
        del payload['episode_id']
        with self.assertRaises(V012ContractError):validate_v012_input(payload)
        payload = copy.deepcopy(self.input)
        payload['undeclared'] = 1
        with self.assertRaises(V012ContractError):validate_v012_input(payload)

    def test_reject_scope_expansion_and_mismatched_ref(self):
        payload = copy.deepcopy(self.input)
        payload['input_references'].append('medication:active')
        with self.assertRaises(V012ContractError):self._call(req=payload)
        payload = copy.deepcopy(self.input)
        payload['documents'][0]['version'] = 2
        with self.assertRaises(V012ContractError):self._call(req=payload)

    def test_reject_document_hash_change(self):
        payload = copy.deepcopy(self.input)
        payload['documents'][0]['text_hash'] = 'sha256:'+'0'*64
        with self.assertRaises(V012ContractError):self._call(req=payload)
        fixture = copy.deepcopy(self.data)
        fixture['GET /documents/DOC-2610060412?version=1']['text'] += 'INJECTED'
        with self.assertRaises(V012ContractError):self._call(data=fixture)

    def test_reject_encounter_or_patient_mismatch(self):
        fixture = copy.deepcopy(self.data)
        fixture['GET /encounters/E261006058']['patient_id'] = 'PT-BAD'
        with self.assertRaises(V012ContractError):self._call(data=fixture)
        fixture = copy.deepcopy(self.data)
        fixture['GET /documents/DOC-2610060412?version=1']['patient_id'] = 'PT-BAD'
        with self.assertRaises(V012ContractError):self._call(data=fixture)

    def test_reject_unknown_structured_context_field(self):
        payload = copy.deepcopy(self.input)
        payload['structured_context']['name_display'] = 'must not be passed to LLM'
        with self.assertRaises(V012ContractError): self._call(req=payload)

    def test_default_produced_time_has_korean_offset(self):
        result = invoke_v012(self.input, execution_id='EXE-TEST-1',
                             data_api=SyntheticFixtureDataAPI(self.data),
                             model=_SyntheticModel())
        from datetime import datetime, timedelta
        self.assertEqual(datetime.fromisoformat(result['produced_time']).utcoffset(),
                         timedelta(hours=9))

    def test_http_client_rejects_out_of_scope_endpoint(self):
        api = HttpSiteDataAPI('http://localhost:9999/chain/api/v0.1',
                              allow_mock_localhost=True)
        with self.assertRaises(ValueError):
            api.get('/encounters/E261006058/observations')
        with self.assertRaises(ValueError):
            api.get('/documents/DOC-2610060412?version=1&unsafe=1')
        with self.assertRaises(ValueError):
            HttpSiteDataAPI('http://example.com/chain/api/v0.1')

    def test_fail_closed_on_bad_llm_output(self):
        with self.assertRaises(ValueError):self._call(model=_InvalidModel())

    def test_invalid_output_missing_key_or_fake_quote(self):
        output = self._call()
        del output['model_info']
        with self.assertRaises(V012ContractError):validate_v012_output(output)
        output = self._call()
        output['evidence'][0]['quote'] = 'FABRICATED'
        docs = [self.data['GET /documents/DOC-2610060412?version=1'],
                self.data['GET /documents/DOC-2610060403?version=2']]
        with self.assertRaises(V012ContractError):validate_v012_output(output,documents=docs)

if __name__=='__main__':unittest.main()
