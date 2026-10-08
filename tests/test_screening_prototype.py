import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from chain_agents.common import canonical_hash
from chain_agents.screening.agent import invoke
from chain_agents.screening.prototype import (
    MODELS, ScreeningLLMBackend, make_messages, screen_documents,
    validate_response, decide_findings,
)

ROOT = Path(__file__).resolve().parents[1]
CASE = json.loads((ROOT/'examples/screening_case.json').read_text(encoding='utf-8'))
DOCS = CASE['documents']
A = 'document:DOC-2610060412@1'
B = 'document:DOC-2610060403@2'


def item(code, quote, status='present', ref=A):
    return {'code': code, 'status': status, 'source_ref': ref, 'quote': quote}

POS = [item('acute_onset', '13:35경 딸과 전화통화 시까지 특이증상 없었다고 함'),
       item('focal_weakness', 'Motor: Rt. U/E G2, Rt. L/E G3, Lt. side G5')]


class FakeModel:
    model_key='fake-synthetic-output'
    model_revision='none'
    def __init__(self, result):
        self.result=result;self.calls=0;self.received=None
    def generate(self, messages):
        self.calls+=1;self.received=messages
        return json.dumps({'findings':self.result}, ensure_ascii=False)


def scope_case(docs=DOCS):
    at='2026-10-06T15:20:00+09:00'
    facts={}
    for doc in docs:
        name=f'document:{doc["document_id"]}@{doc["version"]}'
        facts[name]={'value':copy.deepcopy(doc),'status':'AVAILABLE',
                     'source_ref': {'system':'SYNTHETIC','record_id':doc['document_id'],
                                    'version':doc['version'],'field':'text'},
                     'source_time':at,'known_at':at}
    snap={'contract_schema':'chain-context/v0.3','known_at':at,'facts':facts}
    snap['snapshot_id']=canonical_hash(snap)
    request={'mode':'screening','input_snapshot_id':snap['snapshot_id'],
             'evaluated_at':at,'scope':list(facts)}
    return request,snap


class PrototypeTests(unittest.TestCase):
    def test_exact_checkpoint_keys_only(self):
        self.assertEqual(set(MODELS),{'qwen35_9b','gemma4_12b_it','medgemma15_4b_it'})
    def test_medgemma_exact_checkpoint_revision(self):
        med = MODELS['medgemma15_4b_it']
        self.assertEqual(med['repo_id'], 'google/medgemma-1.5-4b-it')
        self.assertEqual(med['revision'], '91850547d9f0b2fdd21aa7c5f4f3d1a8a52c243b')
        self.assertEqual(med['directory'], 'medgemma-1.5-4b-it')
        self.assertFalse(any('2.5' in spec['repo_id'] for spec in MODELS.values()))

    def test_positive_one_llm_call_and_no_mutation(self):
        model=FakeModel(POS)
        before=copy.deepcopy(DOCS)
        output=screen_documents(model,DOCS,CASE['structured_context'])
        self.assertEqual(output['screening_result'],'POSITIVE')
        self.assertEqual(model.calls,1)
        self.assertEqual(DOCS,before)
        self.assertEqual(len(output['evidence']),2)
    def test_unknown_not_converted_to_negative(self):
        self.assertEqual(screen_documents(FakeModel([]),DOCS)['screening_result'],'REVIEW_REQUIRED')
        self.assertEqual(screen_documents(FakeModel([POS[1]]),DOCS)['screening_result'],'REVIEW_REQUIRED')
    def test_negative_requires_explicit_general_exam(self):
        example=[{'document_id':'NEG-1','version':1,'text':'신경학적 국소 결손 없음.'}]
        f=[item('no_focal_deficit','신경학적 국소 결손 없음.',ref='document:NEG-1@1')]
        self.assertEqual(screen_documents(FakeModel(f),example)['screening_result'],'NEGATIVE')
    def test_unsupported_quote_and_wrong_source_rejected(self):
        for evidence in [[item('acute_onset','not in note')],
                         [item('acute_onset','Motor: Rt. U/E G2, Rt. L/E G3, Lt. side G5',ref=B)]]:
            with self.assertRaises(ValueError):screen_documents(FakeModel(evidence),DOCS)
    def test_last_known_well_alias_normalized_not_loosened(self):
        quote = '마지막 정상 확인 13:35'
        item_alias = item('last_known_well', quote, ref=B)
        original = copy.deepcopy(item_alias)
        result = validate_response({'findings': [item_alias]}, DOCS)
        self.assertEqual(result[0]['code'], 'lkw')
        self.assertEqual(item_alias, original)
        # Alias and canonical name describe exactly the same fact:
        # they must still trigger duplicate evidence rejection.
        with self.assertRaisesRegex(ValueError, 'Duplicate evidence'):
            validate_response({'findings': [item_alias, item('lkw', quote, ref=B)]}, DOCS)
        # Normalization does not disable verbatim quote verification.
        with self.assertRaisesRegex(ValueError, 'exact substring'):
            validate_response({'findings': [item('last_known_well', 'fabricated', ref=B)]}, DOCS)
        # Unknown label remains invalid.
        with self.assertRaisesRegex(ValueError, 'Invalid findings'):
            validate_response({'findings': [item('maybe_lkw', quote, ref=B)]}, DOCS)

    def test_medgemma_output_first_prompt_only_for_medgemma(self):
        med = make_messages(DOCS, model_key='medgemma15_4b_it')
        qwen = make_messages(DOCS, model_key='qwen35_9b')
        self.assertIn('Start with the JSON immediately', med[1]['content'])
        self.assertIn('Babinski is not FAST', med[0]['content'])
        self.assertNotIn('Start with the JSON immediately', qwen[1]['content'])
        self.assertEqual(json.loads(qwen[1]['content'])['documents'][0]['source_ref'], A)
        self.assertIn('\"source_ref\": \"document:DOC-2610060412@1\"', med[1]['content'])


    def test_medgemma_final_channel_json_is_extracted_and_verified(self):
        # The medgemma final marker may follow a visible, non-JSON trace.
        class MedGemmaResponse:
            model_key = 'medgemma15_4b_it'
            model_revision = 'synthetic'
            def __init__(self, response):
                self.response = response
            def generate(self, messages):
                return self.response
        answer = json.dumps({'findings': POS}, ensure_ascii=False)
        raw = '<unused94>thought\nUntrusted model reasoning.\n<unused95>```json\n' + answer + '\n```'
        result = screen_documents(MedGemmaResponse(raw), DOCS)
        self.assertEqual(result['screening_result'], 'POSITIVE')
        self.assertEqual(result['evidence'], POS)
        # A truncated final JSON must still be rejected and raw output retained.
        truncated = '<unused94>thought\nReasoning\n<unused95>```json\n{"findings": ['
        with self.assertRaisesRegex(ValueError, 'Malformed fenced JSON'):
            screen_documents(MedGemmaResponse(truncated), DOCS)
        # JSON shape alone is not enough: quote must come from the named document.
        ungrounded = json.dumps({'findings': [item('focal_weakness', 'fabricated quote')]})
        with self.assertRaisesRegex(ValueError, 'exact substring'):
            screen_documents(MedGemmaResponse('<unused94>thought\n...<unused95>' + ungrounded), DOCS)

    def test_medgemma_incomplete_reasoning_is_rejected(self):
        response = '<unused94>thought\nAnalyze documents and then create JSON...'
        with self.assertRaisesRegex(ValueError, 'reasoning trace'):
            validate_response(response, DOCS)

    def test_unrecognized_code_or_keys_fail(self):
        with self.assertRaises(ValueError):validate_response({'findings':[item('treatment','anything')]},DOCS)
        with self.assertRaises(ValueError):validate_response({'findings':POS,'advice':'tPA'},DOCS)
    def test_no_version_or_text_rejected(self):
        with self.assertRaises(ValueError):make_messages([{'document_id':'x','version':1}])
        with self.assertRaises(ValueError):make_messages([{'document_id':'x','version':0,'text':'abc'}])
    def test_contradictory_evidence_deferred(self):
        evidence=POS+[item('focal_weakness','Motor: Rt. U/E G2, Rt. L/E G3, Lt. side G5','absent')]
        self.assertEqual(screen_documents(FakeModel(evidence),DOCS)['screening_result'],'REVIEW_REQUIRED')
    def test_v03_real_backend_positive_contract(self):
        req,snap=scope_case();original=copy.deepcopy((req,snap))
        result=invoke(req,snap,SimpleNamespace(backend=ScreeningLLMBackend(FakeModel(POS))))
        self.assertEqual(set(result),{'screening_result','mock_only','basis'})
        self.assertEqual(result['screening_result'],'POSITIVE')
        self.assertIs(result['mock_only'],False)
        self.assertEqual((req,snap),original)
    def test_v03_review_fails_safe(self):
        req,snap=scope_case()
        with self.assertRaisesRegex(ValueError,'REVIEW_REQUIRED'):
            invoke(req,snap,SimpleNamespace(backend=ScreeningLLMBackend(FakeModel([]))))
    def test_v03_negative_has_basis(self):
        doc={'document_id':'NEG-1','version':1,'text':'신경학적 국소 결손 없음.'}
        req,snap=scope_case([doc])
        out=invoke(req,snap,SimpleNamespace(backend=ScreeningLLMBackend(FakeModel([
            item('no_focal_deficit','신경학적 국소 결손 없음.',ref='document:NEG-1@1')]))))
        self.assertEqual(out['screening_result'],'NEGATIVE')
        self.assertTrue(out['basis'])
    def test_invalid_scoped_doc_unavailable(self):
        req,snap=scope_case(); snap['facts'][next(iter(snap['facts']))]['status']='PENDING'
        with self.assertRaisesRegex(ValueError,'Document text unavailable'):
            invoke(req,snap,SimpleNamespace(backend=ScreeningLLMBackend(FakeModel(POS))))
    def test_document_source_not_mixed(self):
        messages=make_messages(DOCS)
        payload=json.loads(messages[1]['content'])
        self.assertEqual(len(payload['documents']),2)
        self.assertEqual(payload['documents'][0]['source_ref'],A)


    def test_evaluation_dataset_and_scoring(self):
        from chain_agents.screening.evaluation import synthetic_cases, evaluate
        cases=synthetic_cases()
        self.assertEqual(len(cases),8)
        self.assertEqual({x['expected_result'] for x in cases},
                         {'POSITIVE','NEGATIVE','REVIEW_REQUIRED'})
        report=evaluate(FakeModel([]), cases)
        self.assertEqual(report['cases'],8)
        self.assertEqual(report['valid_output_rate'],1.0)
        self.assertEqual(report['exact_label_accuracy_all_cases'],4/8)


if __name__=='__main__':unittest.main()
