"""Run the Summary Agent against a synthetic input or a local model."""
import argparse
import copy
import json
from pathlib import Path
from chain_agents.summary.agent import invoke
from chain_agents.summary.data_contract import FixtureDataAPI
from chain_agents.services import AgentServices

class FixtureExtractor:
    model_key = 'synthetic-fixture'
    method = 'fixture'
    def __init__(self, payload): self.payload = copy.deepcopy(payload)
    def extract(self, documents, questions): return copy.deepcopy(self.payload)

def run_fixture(fixture=None, extractor=None):
    if fixture is None:
        fixture = json.loads(Path(__file__).with_name('summary_fixture.json').read_text(encoding='utf-8'))
    if extractor is None:
        extractor = FixtureExtractor(fixture['synthetic_extraction'])
    services = AgentServices(
        data_api=FixtureDataAPI(fixture['api_responses']),
        extractor=extractor,
    )
    return invoke(fixture['request'], None, services)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', choices=['qwen35_9b', 'gemma4_12b_it', 'medgemma15_4b_it'])
    parser.add_argument('--model-dir', type=Path)
    parser.add_argument('--gpu')
    args = parser.parse_args()
    fixture = json.loads(Path(__file__).with_name('summary_fixture.json').read_text(encoding='utf-8'))
    if args.model:
        if args.model_dir is None or args.gpu is None:
            parser.error('--model requires --model-dir and --gpu')
        from chain_agents.summary.extractor import LocalSummaryExtractor
        extractor = LocalSummaryExtractor(args.model, args.model_dir, gpu=args.gpu)
    else:
        if args.model_dir is not None or args.gpu is not None:
            parser.error('--model-dir / --gpu require --model')
        extractor = FixtureExtractor(fixture['synthetic_extraction'])
    result = run_fixture(fixture, extractor)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
