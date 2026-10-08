"""Reproducible typed-schema benchmark for the first S1 Summary invocation."""
import argparse
import copy
import hashlib
from importlib.metadata import version as package_version
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
import time
from pathlib import Path
from types import SimpleNamespace

from .history_s1_contract import (
    QUESTION_CATALOG, canonical_questions, canonical_value, finalize_facts, validate_final_items,
)
from .history_s1_cases import cases
from .history_s1_extractor import (
    DIRECT_PROMPT, EVIDENCE_FIRST_PROMPT, FIELD_ORDERS, MAX_NEW_TOKENS, LocalS1Extractor,
)
from .history_s1_summary import run_history
from .mock_contract import FixtureDataAPI, resolve

MODELS = ['qwen35_9b', 'gemma4_12b_it']
METHODS = ['direct', 'evidence_first']
GPU_ASSIGNMENTS = {'qwen35_9b': '2', 'gemma4_12b_it': '3'}
DEFAULT_ROOT = Path('/data/data2/jhbak/CHAIN_agent_summary_prototype/outputs/summary_s1_gt_review_parallel_20261008')


def save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def _sources(case):
    reader = FixtureDataAPI(case['api_responses'])
    resources = resolve(case['request'], reader)
    docs = {ref: value for ref, value in resources.items() if ref.startswith('document:')}
    return reader, resources, docs


def _oracle_payload(case, docs):
    facts = []
    for item in case['gold_items']:
        status = item['status']
        if status in ('documented', 'explicitly_unknown'):
            facts.append({k: copy.deepcopy(item[k]) for k in ('question', 'status', 'value', 'evidence')})
        elif status == 'conflicting':
            for alternative in item['alternatives']:
                facts.append({'question': item['question'], 'status': 'documented',
                              'value': copy.deepcopy(alternative['value']),
                              'evidence': copy.deepcopy(alternative['evidence'])})
    return {'facts': facts, 'reviewed_documents': list(docs)}


def _gold_equivalent(actual, expected):
    if len(actual) != len(expected):
        return False
    for left, right in zip(actual, expected):
        q = right['question']
        if left['question'] != q or left['status'] != right['status']:
            return False
        if right['status'] == 'conflicting':
            a = sorted(json.dumps(canonical_value(x['value'], q), sort_keys=True, ensure_ascii=False) for x in left['alternatives'])
            b = sorted(json.dumps(canonical_value(x['value'], q), sort_keys=True, ensure_ascii=False) for x in right['alternatives'])
            if a != b:
                return False
        elif canonical_value(left['value'], q) != canonical_value(right['value'], q):
            return False
        if left['evidence'] != right['evidence']:
            return False
    return True


def prepare(root):
    root = Path(root).resolve()
    if not any(root.is_relative_to(Path(base)) for base in ('/data/data2', '/data/data3')):
        raise ValueError('All experiment data must be under /data/data2 or /data/data3')
    root.mkdir(parents=True, exist_ok=False)
    dataset = cases()
    os.environ['CUDA_VISIBLE_DEVICES'] = '2'
    import torch
    import transformers
    oracle_checks = []
    for case in dataset:
        reader, resources, docs = _sources(case)
        gold = case['gold_items']
        questions = case['questions']
        validate_final_items(gold, questions, resources)
        payload = _oracle_payload(case, docs)
        result = finalize_facts(payload, docs, questions, evidence_sources=resources)
        validate_final_items(result, questions, resources)
        if not _gold_equivalent(result, gold):
            raise ValueError(f'Code-only reconciliation did not reproduce revised GT for {case["case_id"]}')
        oracle_checks.append({'case_id': case['case_id'], 'field_count': len(gold), 'valid': True})
    save(root / 'cases.json', dataset)
    save(root / 'question_catalog.json', QUESTION_CATALOG)
    (root / 'direct_prompt.txt').write_text(DIRECT_PROMPT, encoding='utf-8')
    (root / 'evidence_first_prompt.txt').write_text(EVIDENCE_FIRST_PROMPT, encoding='utf-8')
    manifest = {
        'schema_version': 'summary-s1-fields/v1',
        'design': 'One S1 invocation returns typed question/status/value/evidence fields; the orchestrator/runtime persists the accepted result.',
        'question_types': {q: spec['type'] for q, spec in QUESTION_CATALOG.items()},
        'request_questions': ['anticoagulant_use', 'recent_surgery_or_bleeding', 'previous_stroke', 'lkw_records'],
        'request_alias_expansion': {'recent_surgery_or_bleeding': ['recent_surgery', 'recent_bleeding'],
                                    'anticoagulant_use': 'also requests antiplatelet_use as in the v0.12 sample'},
        'case_count': len(dataset),
        'fields_per_case': len(dataset[0]['questions']),
        'expected_fields': sum(len(case['gold_items']) for case in dataset),
        'models': MODELS,
        'methods': METHODS,
        'experiment': 'reviewed_GT_and_common_status_rules; single_call_field_order_comparison',
        'annotation_version': 's1-gold-review-v2',
        'extraction_rule_version': 's1-status-v2',
        'field_orders': FIELD_ORDERS,
        'llm_calls_per_case': 1,
        'only_prompt_difference': 'question,status,value,evidence -> question,evidence,status,value',
        'gpu_assignments': GPU_ASSIGNMENTS,
        'parallel_models': True,
        'runtime': {
            'python_version': platform.python_version(),
            'transformers_version': transformers.__version__,
            'torch_version': torch.__version__,
            'torchaudio_version': package_version('torchaudio'),
            'tokenizers_version': package_version('tokenizers'),
            'safetensors_version': package_version('safetensors'),
            'huggingface_hub_version': package_version('huggingface-hub'),
            'cuda_version': torch.version.cuda,
            'gpu_name_visible_as_0': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        },
        'max_new_tokens_per_generation': MAX_NEW_TOKENS,
        'decoding': 'greedy (do_sample=false)',
        'dataset_sha256': hashlib.sha256((root / 'cases.json').read_bytes()).hexdigest(),
        'direct_prompt_sha256': hashlib.sha256(DIRECT_PROMPT.encode()).hexdigest(),
        'evidence_first_prompt_sha256': hashlib.sha256(EVIDENCE_FIRST_PROMPT.encode()).hexdigest(),
        'code_only_gold_checks': oracle_checks,
        'annotation_note': 'All records are synthetic. Gold was manually revised before inference and was not clinician-adjudicated.',
        'persistence_boundary': 'The agent returns a versioned Summary object; the orchestrator/runtime owns accepted-result storage and result_ref publication. This benchmark additionally saves raw generations and results under this output directory.',
    }
    assert EVIDENCE_FIRST_PROMPT.replace(
        'Each fact has EXACTLY question, evidence, status, value.',
        'Each fact has EXACTLY question, status, value, evidence.',
    ) == DIRECT_PROMPT
    snapshot = root / 'source_snapshot'
    snapshot.mkdir()
    manifest['source_sha256'] = {}
    for name in ('history_s1_extractor.py', 'history_s1_contract.py', 'history_s1_summary.py',
                 'history_s1_cases.py', 'history_s1_experiment.py', 'history_s1_report.py', 'history_s1_gt_audit.py', 'experiment.py'):
        content = Path(__file__).with_name(name).read_bytes()
        (snapshot / name).write_bytes(content)
        manifest['source_sha256'][name] = hashlib.sha256(content).hexdigest()
    from .history_s1_gt_audit import build_audit
    save(root / 'gt_review.json', build_audit(dataset))
    save(root / 'manifest.json', manifest)
    print('PREPARED', root, flush=True)


def _load_extractor(model, gpu=None):
    from .experiment import MODELS as MODEL_SPECS
    base = Path('/data/data2/jhbak/CHAIN_agent_summary_prototype')
    os.environ.setdefault('HF_HOME', str(base / 'hf_cache'))
    os.environ.setdefault('TMPDIR', str(base / 'runtime/tmp'))
    model_spec = MODEL_SPECS[model]
    gpu = str(gpu if gpu is not None else GPU_ASSIGNMENTS[model])
    extractor = LocalS1Extractor(model, base / 'models' / model_spec['directory'], gpu=gpu,
                                 max_new_tokens=MAX_NEW_TOKENS, method=METHODS[0])
    extractor.runtime_info = {
        'python_version': platform.python_version(),
        'transformers_version': __import__('transformers').__version__,
        'torch_version': extractor.backend.torch.__version__,
        'torchaudio_version': package_version('torchaudio'),
        'tokenizers_version': package_version('tokenizers'),
        'safetensors_version': package_version('safetensors'),
        'huggingface_hub_version': package_version('huggingface-hub'),
        'cuda_version': extractor.backend.torch.version.cuda,
        'gpu_requested': gpu,
        'pid': os.getpid(),
        'model_device_map': {k: str(v) for k, v in getattr(extractor.backend.model, 'hf_device_map', {}).items()},
        'gpu_name_visible_as_0': extractor.backend.torch.cuda.get_device_name(0),
    }
    return extractor


def run_model(root, model, method, extractor=None, gpu=None):
    from .experiment import MODELS as MODEL_SPECS

    root = Path(root).resolve()
    if not any(root.is_relative_to(Path(base)) for base in ('/data/data2', '/data/data3')):
        raise ValueError('All experiment data must be under /data/data2 or /data/data3')
    if model not in MODELS or method not in METHODS:
        raise ValueError('Unsupported model or method')
    cases_path = root / 'cases.json'
    if not cases_path.is_file():
        raise ValueError('Run --prepare before inference')
    output_path = root / f'{method}_{model}.json'
    if output_path.exists():
        raise FileExistsError(f'Preserving existing run; choose a fresh output root: {output_path}')
    data = json.loads(cases_path.read_text(encoding='utf-8'))
    if extractor is None:
        extractor = _load_extractor(model, gpu)
    elif extractor.model_key != model:
        raise ValueError('A reused extractor must belong to the requested model')
    extractor.method = method
    model_spec = MODEL_SPECS[model]
    results = []
    started_at = datetime.now(timezone.utc).isoformat()
    for case in data:
        reader, _, docs = _sources(case)
        extractor.last_generation = None
        extractor.payload = None
        extractor.details = None
        started = time.perf_counter()
        result, failure = None, None
        try:
            result = run_history(case['request'], None,
                                 SimpleNamespace(summary_data_api=reader, summary_extractor=extractor))
        except Exception as exc:
            failure = {'type': type(exc).__name__, 'detail': str(exc)}
        entry = {
            'case_id': case['case_id'],
            'questions': list(case['questions']),
            'result': result,
            'failure': failure,
            'payload': extractor.payload,
            'generation': extractor.last_generation or {'generated_tokens': 0, 'cap_reached': False},
            'details': extractor.details,
            'elapsed_seconds': time.perf_counter() - started,
            'generation_calls': extractor.generation_calls,
        }
        results.append(entry)
        save(output_path, {'model': model, 'model_name': model_spec.get('display_name', model),
                           'revision': model_spec.get('revision'), 'method': method,
                           'runtime': getattr(extractor, 'runtime_info', None), 'started_at': started_at,
                           'updated_at': datetime.now(timezone.utc).isoformat(), 'results': results})
        generation = entry['generation']
        print(method, model, case['case_id'], generation.get('generated_tokens', 0),
              round(entry['elapsed_seconds'], 1), 'OK' if result is not None else failure, flush=True)
    print('FINISHED', method, model, output_path, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=str(DEFAULT_ROOT))
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--model', choices=MODELS)
    parser.add_argument('--gpu', choices=['2', '3'])
    parser.add_argument('--method', choices=METHODS)
    args = parser.parse_args()
    if args.prepare:
        prepare(args.root)
    elif args.model and args.method:
        run_model(args.root, args.model, args.method, gpu=args.gpu)
    elif args.model:
        extractor = _load_extractor(args.model, args.gpu)
        for method in METHODS:
            run_model(args.root, args.model, method, extractor=extractor)
    elif args.method:
        parser.error('--model and --method must be supplied together')
    else:
        if args.gpu:
            parser.error('--gpu requires --model; parallel mode uses GPU 2 and 3')
        workers, logs = [], []
        try:
            for model in MODELS:
                gpu = GPU_ASSIGNMENTS[model]
                log = (Path(args.root) / f'{model}.log').open('w', encoding='utf-8')
                logs.append(log)
                env = dict(os.environ, CUDA_VISIBLE_DEVICES=gpu)
                proc = subprocess.Popen([sys.executable, '-m', 'chain_agents.summary.history_s1_experiment',
                    '--root', args.root, '--model', model, '--gpu', gpu], env=env, stdout=log, stderr=subprocess.STDOUT)
                workers.append((model, gpu, proc))
                print('STARTED', model, 'GPU', gpu, 'PID', proc.pid, flush=True)
            save(Path(args.root) / 'workers.json', [{'model': m, 'gpu': g, 'pid': p.pid} for m,g,p in workers])
            statuses = {m: p.wait() for m, g, p in workers}
            save(Path(args.root) / 'worker_exit_codes.json', statuses)
            if any(statuses.values()):
                raise RuntimeError(f'Worker errors: {statuses}')
            (Path(args.root) / 'DONE').write_text('both models completed on separate GPUs\n', encoding='ascii')
            print('FINISHED parallel models', statuses, flush=True)
        finally:
            for _, _, proc in workers:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
            for log in logs:
                log.close()



if __name__ == '__main__':
    main()
