#!/usr/bin/env python3
"""Download the pinned model or run its synthetic offline Summary experiment."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from chain_agents.summary.experiment import download_model, run_experiment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("download", help="Download the pinned public checkpoint under /data/data2 or /data/data3.")
    run = subparsers.add_parser("run", help="Run only local inference on synthetic notes.")
    run.add_argument("--gpu", default="0", help="Physical GPU index.")
    run.add_argument("--max-new-tokens", type=int, default=1800)
    run.add_argument("--case-limit", type=int, default=None, help="Optional smoke run on first N cases.")
    args = parser.parse_args()
    if args.command == "download":
        download_model()
    else:
        run_experiment(args.gpu, args.max_new_tokens, args.case_limit)


if __name__ == "__main__":
    main()
