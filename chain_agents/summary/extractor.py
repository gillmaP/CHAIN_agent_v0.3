"""Typed, quote-grounded S1 extraction: one-pass and quote-first variants."""
import json
import time

from .local_model import LocalModel
from .contract import QUESTION_CATALOG, validate_model_payload

MAX_NEW_TOKENS = 8192

DIRECT_PROMPT = '''You extract facts for the initial S1 Clinical Summary. Work only from the supplied narrative documents and fixed question catalog. Return only one JSON object with exactly: {"facts": [...], "reviewed_documents": [...]}.
Each fact has EXACTLY question, status, value, evidence. Each evidence entry has EXACTLY source_ref and quote. Do not output an assertion/polarity property.

STATUS RULES:
- documented: the source explicitly provides a value. A documented negative is status=documented with value=false for boolean questions. A documented positive is status=documented with value=true. These rules are identical for anticoagulant_use and antiplatelet_use.
- explicitly_unknown: the source explicitly says unknown, unavailable, could not be confirmed, not asked, or not assessed (모름, 확인 불가, 미문진, 문진하지 않음, 다루지 않음). Use value=null and cite that statement. This is not a denial of the clinical condition. Never convert a statement about not asking or not knowing into documented/false.
- not_stated: no supplied document addresses the question at all after every document is reviewed. You may omit the fact or emit the full four-key fact with status=not_stated, value=null, evidence=[]. Never omit required keys in an emitted fact. Code reconciles this marker with other facts and structured sources; a supported documented or explicitly_unknown fact takes precedence over a no-mention marker. An explicit statement of non-assessment is explicitly_unknown, not not_stated.
- Do NOT emit conflicting. Keep each incompatible source statement as its own documented fact; code compares values and creates conflict alternatives.
- Do NOT emit not_applicable for this question set.

QUESTION-SPECIFIC RULES:
- Boolean values must be JSON true or false, never strings such as "present"/"absent", never 0/1. Do not infer false from silence or from a local medication/problem list having no matching row.
- recent_surgery and recent_bleeding are separate questions. A negative answer to one says nothing about the other. Do not merge them.
- previous_stroke means this patient's past stroke/TIA. Exclude relatives and the current suspected episode.
- lkw_records means last known well for the current episode, not symptom onset, discovery/recognition, or note-entry time. Return a time object with EXACTLY kind, start, end, precision, original_text. Kinds: point, approximate, interval, before, after, partial. Precision: second, minute, hour, day, unknown. Timestamps must include timezone. Shape rules are strict: point -> start=timestamp,end=null; approximate -> start=normalized approximate timestamp,end=null; interval -> start=lower bound,end=upper bound; before -> start=null,end=upper bound; after -> start=lower bound,end=null; partial date-only -> start=YYYY-MM-DD,end=null,precision=day. Use both null endpoints only for partial with precision=unknown and preserve the phrase in original_text. Do not put the same point in both start and end. For a minute-level time, format seconds as :00 and set precision=minute. For an hour-level approximate time such as "오늘 15시쯤", use 15:00:00 with precision=hour and kind=approximate; this does not claim an exact 15:00. Preserve approximation/range; never invent exactness. original_text must be a verbatim contiguous phrase from the source. Use the document date to resolve relative dates only when supplied by saved_time/document context.
- If multiple documents agree on one value, you may emit one fact with multiple evidence entries. If they disagree about the same patient/question/time scope, keep separate facts with their own evidence. Do not treat resolved historical changes or different events as conflicts.

EVIDENCE RULES:
- Copy verbatim, contiguous text from the cited source. Use enough context for negation, person, current/past status, and time. If multiple separated sentences are needed, use multiple evidence entries; do not splice text or translate.
- source_ref must exactly match an input reference. reviewed_documents must list every supplied document reference exactly once, including documents with no relevant statement.
- Use only the fixed question IDs supplied. Do not answer unrequested concepts. Do not include confidence, prose, derived clinical conclusions, or treatment recommendations.

Question definitions (including each answer type) are supplied in the user message.'''

# Both arms differ only in the order of the same four field names.
DIRECT_PROMPT += "\nEmit each fact's keys in the order listed above."
EVIDENCE_FIRST_PROMPT = DIRECT_PROMPT.replace(
    'Each fact has EXACTLY question, status, value, evidence.',
    'Each fact has EXACTLY question, evidence, status, value.',
)
FIELD_ORDERS = {
    'direct': ['question', 'status', 'value', 'evidence'],
    'evidence_first': ['question', 'evidence', 'status', 'value'],
}


def _decode(raw, required_key):
    if '<unused94>thought' in raw:
        if '<unused95>' not in raw:
            raise ValueError('No final response marker')
        raw = raw.rsplit('<unused95>', 1)[1]
    decoder = json.JSONDecoder()
    found = []
    for index, char in enumerate(raw):
        if char != '{':
            continue
        try:
            value, _ = decoder.raw_decode(raw[index:])
        except ValueError:
            continue
        if isinstance(value, dict) and required_key in value:
            found.append(value)
    if not found:
        raise ValueError(f'No complete JSON object containing {required_key}')
    return found[-1]


def _question_specs(questions):
    return [{'question': q, **QUESTION_CATALOG[q]} for q in questions]


class LocalS1Extractor:
    def __init__(self, model_key, model_dir, gpu=None, max_new_tokens=MAX_NEW_TOKENS, method='direct'):
        if method not in ('direct', 'evidence_first'):
            raise ValueError('method must be direct or evidence_first')
        gpu = str(gpu if gpu is not None else {'qwen35_9b': '2', 'gemma4_12b_it': '3'}[model_key])
        self.backend = LocalModel(model_key, model_dir, gpu_index=gpu, max_new_tokens=max_new_tokens)
        self.model_key = model_key
        self.gpu = str(gpu)
        self.limit = max_new_tokens
        self.method = method
        self.generation_calls = 0
        self.last_generation = None
        self.payload = None
        self.details = None

    def _generate(self, system, user):
        self.generation_calls += 1
        backend = self.backend
        messages = [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': json.dumps(user, ensure_ascii=False)},
        ]
        options = dict(add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors='pt')
        if self.model_key == 'qwen35_9b':
            options['enable_thinking'] = False
        inputs = backend.processor.apply_chat_template(messages, **options).to(backend.model.device)
        started = time.perf_counter()
        with backend.torch.inference_mode():
            output = backend.model.generate(**inputs, max_new_tokens=self.limit, do_sample=False, use_cache=True)
        tokens = output[0, inputs['input_ids'].shape[-1]:]
        raw = backend.processor.decode(tokens, skip_special_tokens=True)
        return {'raw': raw, 'generated_tokens': len(tokens), 'cap_reached': len(tokens) >= self.limit,
                'elapsed_seconds': time.perf_counter() - started}

    def extract(self, documents, questions):
        self.generation_calls = 0
        self.last_generation = None
        self.payload = None
        self.details = None
        docs = [{'source_ref': ref, 'saved_time': doc.get('saved_time'), 'text': doc['text']}
                for ref, doc in documents.items()]
        catalog = _question_specs(questions)
        prompt = DIRECT_PROMPT if self.method == 'direct' else EVIDENCE_FIRST_PROMPT
        generation = self._generate(prompt, {'questions': catalog, 'documents': docs})
        generation['generation_calls'] = self.generation_calls
        self.last_generation = generation
        if generation['cap_reached']:
            raise ValueError('S1 extraction reached token limit')
        payload = _decode(generation['raw'], 'facts')
        self.details = {'parsed_payload': payload, 'expected_field_order': FIELD_ORDERS[self.method]}
        if not isinstance(payload, dict) or set(payload) != {'facts', 'reviewed_documents'}:
            raise ValueError('Output must contain facts and reviewed_documents only')
        # Report actual generation order separately; do not reject a correct answer for key order.
        facts = payload.get('facts')
        if isinstance(facts, list):
            orders = [list(f) for f in facts if isinstance(f, dict)]
            self.details['observed_field_orders'] = orders
            self.details['order_checked_facts'] = len(orders)
            self.details['order_followed_facts'] = sum(o == FIELD_ORDERS[self.method] for o in orders)
        validate_model_payload(payload, documents, questions)
        self.payload = payload
        return payload
