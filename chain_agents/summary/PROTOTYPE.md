# Summary LLM prototype

This branch supports four pinned zero-shot candidates for the same four synthetic Korean stroke-note cases: Qwen3.5-9B, Qwen2.5-14B-Instruct, Gemma 4 12B IT, and MedGemma 1.5 4B IT. The prompt, output schema, deterministic decoding settings, and scoring code are shared. Text-only causal and multimodal Transformers loaders are selected by model. MedGemma is gated and requires account access before it can be downloaded.

## CHAIN v0.3 boundary

The public invoke(request, snapshot, services) entrypoint and logic.run() stay unchanged. The current orchestrator uses Summary as a structured-context service and requires structured_context to exactly equal snapshot.facts. Its declared output has no narrative-summary field. The LLM experiment therefore runs separately from the registered plugin. Integration into invoke() needs an agreed result-contract change with the orchestration team.

## Storage and execution

Weights, Hugging Face cache, predictions, metrics, and runtime metadata go under /data/data2/jhbak/CHAIN_agent_summary_prototype. CHAIN_SUMMARY_DATA_DIR may point to another directory under /data/data2 or /data/data3; the code checks this. The Git repository contains code and synthetic cases only.

From the repository root inside jhbak_ct:

    python scripts/summary_experiment.py download --model qwen35_9b
    python scripts/summary_experiment.py run --model qwen35_9b --gpu 1

Use model keys qwen25_14b_instruct, gemma4_12b_it, and medgemma15_4b_it for the other candidates. MedGemma requires Hugging Face access after accepting the HAI-DEF Terms of Use. Downloads are pinned to exact revisions. Inference loads local-only weights, uses greedy generation, and blocks Hub access. Gemma 4 uses the isolated runtime at /data/data2/jhbak/CHAIN_agent_summary_prototype/runtime/gemma4-venv/bin/python because the container runtime does not support its architecture. Run files go to model-specific timestamped outputs/ directories under the data folder.

The synthetic set covers Korean/English notes, negation, uncertainty, patient versus family history, event time versus note-entry time, medication/dose, numeric units, explicitly unknown LKW, and conflicting onset times. Reported measures are JSON/schema validity, claim precision/recall/F1, exact quote support, exact event-time agreement, value agreement on aligned claims, and generation time. Claim P/R/F1 compares sets of signatures (subject, concept, polarity, temporality, event time, and source document) from all JSON-valid cases; duplicate signatures collapse. Value agreement and quote support are separate measures. A schema error in one claim does not discard the other parsed claims, and schema validity remains a separate rate. Event-time agreement is recall over expected event-time signatures. Review the Korean text manually too. This small synthetic set is not clinical validation.

## Model and runtime

Model IDs, revisions, and license labels are defined in experiment.py. Qwen runs use the existing CUDA-enabled environment in jhbak_ct. Gemma 4 uses an isolated CUDA 12.6 PyTorch 2.8 / Transformers 5.10.4 environment under data2; the shared container packages are unchanged.

Only synthetic records are used. Do not put real patient data in Git or send it to hosted services. The prototype extracts source statements; it does not diagnose, recommend treatment, or determine tPA eligibility. A synthetic run does not establish clinical safety or readiness.
