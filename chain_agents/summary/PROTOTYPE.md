# Summary LLM prototype

## Output contract

The experiment uses the structured output format in OUTPUT_SCHEMA.md: a concise Korean
summary plus source-grounded items. Absence, uncertainty, explicitly unknown
information, measurements, the person affected, the person reporting it, event time,
and note-entry time have distinct representations. The model omits unavailable
optional fields rather than outputting null.

## CHAIN v0.3 boundary

The public invoke(request, snapshot, services) entrypoint and logic.run() stay
unchanged. The current orchestrator uses Summary as a structured-context service and
requires structured_context to exactly equal the input snapshot.facts. Its declared
output has no narrative-summary field. The LLM experiment therefore runs separately
from the registered plugin. Integrating it into invoke() needs an agreed result
contract change with the orchestration team.

## Candidates and execution

Four pinned zero-shot candidates are compared on the same four synthetic Korean
stroke-note cases: Qwen3.5-9B, Qwen2.5-14B-Instruct, Gemma 4 12B IT, and MedGemma
1.5 4B IT. The prompt, output schema, deterministic decoding settings, and scoring
code are shared. MedGemma requires Hugging Face access after accepting HAI-DEF terms.

Weights, Hugging Face cache, predictions, metrics, and runtime metadata go under
/data/data2/jhbak/CHAIN_agent_summary_prototype. CHAIN_SUMMARY_DATA_DIR may point
to another directory under /data/data2 or /data/data3; the code checks this. The
Git repository contains code and synthetic cases only.

From the repository root inside jhbak_ct:

    python scripts/summary_experiment.py download --model medgemma15_4b_it
    python scripts/summary_experiment.py run --model qwen35_9b --gpu 1

Use model keys qwen25_14b_instruct, gemma4_12b_it, and medgemma15_4b_it for the
other candidates. Downloads are pinned to exact revisions. Inference loads local-only
weights, uses greedy generation, and blocks Hub access. Gemma 4 uses the isolated
runtime at /data/data2/jhbak/CHAIN_agent_summary_prototype/runtime/gemma4-venv/bin/python.
Run files are timestamped under the data directory.

Reported measures are JSON/schema validity, source-grounded fact precision/recall/F1,
exact quote support, exact event-time agreement, value/unit agreement on aligned facts,
and generation time. Core fact metrics compare source-aware signatures; reporter accuracy, values, units,
and evidence are assessed separately. The case breakdown keeps missing and extra items visible.
Review the Korean text manually too. This four-case synthetic set is not clinical
validation.

Only synthetic records are used. Do not put real patient data in Git or send it to
hosted services. The prototype extracts source statements; it does not diagnose,
recommend treatment, or determine tPA eligibility.
