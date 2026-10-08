#!/usr/bin/env python3
"""Run Team 1's stroke screening with an explicitly selected local model.

'smoke' verifies parsing/contract using synthetic prepared output, not inference.
'run' performs actual local Qwen3.5-9B, Gemma4-12B-it, or MedGemma1.5-4B-it inference.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from chain_agents.screening.local_model import LocalScreeningModel, download_model, verify_local_model
from chain_agents.screening.prototype import MODELS, screen_documents, ScreeningResponseError
from chain_agents.screening.evaluation import evaluate


class PreparedSyntheticOutput:
    model_key = 'synthetic-output-no-llm'
    model_revision = 'none'
    def generate(self, messages):
        data = json.loads(messages[1]['content'])
        docs = {doc['source_ref']: doc['text'] for doc in data['documents']}
        # This fixture is explicitly limited to mock_v0.12_stroke_reference_001.
        a = 'document:DOC-2610060412@1'
        b = 'document:DOC-2610060403@2'
        evidence = [
            {'code': 'acute_onset', 'status': 'present', 'source_ref': a,
             'quote': '13:35경 딸과 전화통화 시까지 특이증상 없었다고 함'},
            {'code': 'focal_weakness', 'status': 'present', 'source_ref': a,
             'quote': 'Motor: Rt. U/E G2, Rt. L/E G3, Lt. side G5'},
            {'code': 'language_or_speech_deficit', 'status': 'present', 'source_ref': a,
             'quote': 'Global aphasia (comprehension 일부 보존), dysarthria'},
            {'code': 'fast_positive', 'status': 'present', 'source_ref': b,
             'quote': 'FAST: Face(+) Arm(+) Speech(+)'},
            {'code': 'lkw', 'status': 'present', 'source_ref': b,
             'quote': '마지막 정상 확인 13:35'},
            {'code': 'symptom_discovery', 'status': 'present', 'source_ref': b,
             'quote': '발생시각 14:20 발견'},
        ]
        for item in evidence:
            if item['source_ref'] not in docs or item['quote'] not in docs[item['source_ref']]:
                raise ValueError('Synthetic smoke case does not match expected mock documents')
        return json.dumps({'findings': evidence}, ensure_ascii=False)


def output_destination(output: Path | None, model_key: str, command: str) -> Path | None:
    """Allow ./results or an explicit JSON path, with private project output only."""
    if output is None:
        return None
    output = output.expanduser().resolve()
    if output.is_dir() or not output.suffix:
        suffix = 'evaluation' if command == 'evaluate' else 'result'
        output = output / f'{model_key}_{suffix}.json'
    elif output.suffix.lower() != '.json':
        raise ValueError('--output must be a .json file or directory')
    if ROOT == output or ROOT in output.parents:
        private_results = ROOT / 'results'
        if private_results not in output.parents:
            raise ValueError('Inside the project, output is allowed only under ./results/')
    return output


def save_private_json(output: Path, obj: dict) -> None:
    """Restrict permissions: raw model text may reproduce patient notes."""
    output.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(output), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as fp:
        json.dump(obj, fp, indent=2, ensure_ascii=False)
        fp.write('\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('smoke', help='Offline parser/rule test with a prepared mock response (NOT LLM).')
    down = sub.add_parser('download', help='Explicitly download the pinned model checkpoint.')
    down.add_argument('--model', required=True, choices=sorted(MODELS))
    down.add_argument('--model-root', type=Path, help='Independent root directory for local model weights')
    chk = sub.add_parser('check-model', help='Verify model config and pinned revision before GPU load.')
    chk.add_argument('--model', required=True, choices=sorted(MODELS))
    chk.add_argument('--model-root', type=Path)
    eva = sub.add_parser('evaluate', help='Offline GPU evaluation on 8 hand-authored synthetic cases.')
    eva.add_argument('--model', choices=sorted(MODELS), default='qwen35_9b')
    eva.add_argument('--gpu', default='0')
    eva.add_argument('--model-root', type=Path)
    eva.add_argument('--max-new-tokens', type=int, default=1800)
    eva.add_argument('--output', type=Path, help='Optional private directory report JSON')
    run = sub.add_parser('run', help='Offline GPU inference on scoped input JSON.')
    run.add_argument('--model', choices=sorted(MODELS), default='qwen35_9b')
    run.add_argument('--gpu', default='0')
    run.add_argument('--model-root', type=Path)
    run.add_argument('--max-new-tokens', type=int, default=1800)
    run.add_argument('--input', type=Path, default=ROOT/'examples/screening_case.json')
    run.add_argument('--output', type=Path, help='Optional output JSON file. Do not store PHI in Git.')
    args = parser.parse_args(argv)
    if getattr(args, 'model_root', None) is not None:
        os.environ['CHAIN_SCREENING_MODEL_ROOT'] = str(args.model_root.expanduser().resolve())
    if args.command == 'check-model':
        print(verify_local_model(args.model)); return
    if args.command == 'download':
        print(download_model(args.model));return
    output_file = (output_destination(args.output, args.model, args.command)
                   if args.command in ('run', 'evaluate') else None)
    if args.command == 'evaluate':
        model = LocalScreeningModel(args.model, gpu=args.gpu, max_new_tokens=args.max_new_tokens)
        report = evaluate(model)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if output_file:
            save_private_json(output_file, report)
            print(f'Saved: {output_file}', file=sys.stderr)
        return
    if args.command == 'smoke':
        path = ROOT/'examples/screening_case.json'
        model = PreparedSyntheticOutput()
    else:
        path = args.input
        model = LocalScreeningModel(args.model, gpu=args.gpu, max_new_tokens=args.max_new_tokens)
    case = json.loads(path.read_text(encoding='utf-8'))
    try:
        result = screen_documents(model, case['documents'], case.get('structured_context'))
    except ScreeningResponseError as exc:
        if output_file is not None:
            # Only write the rejected response if --output was requested.
            # No automatic label is substituted for a failed schema validation.
            invalid_file = output_file.with_name(output_file.stem + '.invalid_raw.json')
            save_private_json(invalid_file, {
                'validation_error': str(exc),
                'model_key': args.model if args.command == 'run' else 'synthetic',
                'raw_llm_response': exc.raw_response,
                'generation_info': getattr(model, 'last_generation_info', None),
                'warning': 'REJECTED raw LLM output, NOT a screening result; may contain patient text.',
            })
            print(f'Rejected LLM output saved: {invalid_file}', file=sys.stderr)
        raise
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if output_file is not None:
        save_private_json(output_file, result)
        print(f'Saved: {output_file}', file=sys.stderr)


if __name__ == '__main__':
    main()
