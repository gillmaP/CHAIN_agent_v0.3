# Summary LLM prototype

This branch adds a zero-shot extraction experiment using the official Qwen3.5-9B checkpoint. It follows useful ClinBench practices: task-specific prompts, machine-readable output validation, a fixed dataset, and accuracy/runtime reporting. ClinBench's English datasets and model rankings do not establish performance on Korean stroke notes.

## CHAIN v0.3 boundary

The public invoke(request, snapshot, services) entrypoint and logic.run() stay unchanged. The current orchestrator uses Summary as a structured-context service and requires structured_context to exactly equal snapshot.facts. Its declared output has no narrative-summary field. The LLM experiment therefore runs separately from the registered plugin. Integration into invoke() needs an agreed result-contract change with the orchestration team.

## Storage and execution

Weights, Hugging Face cache, predictions, metrics, and runtime metadata go under /data/data2/jhbak/CHAIN_agent_summary_prototype. CHAIN_SUMMARY_DATA_DIR may point to another directory under /data/data2 or /data/data3; the code checks this. The Git repository contains code and synthetic cases only.

From the repository root inside jhbak_ct:

    python scripts/summary_experiment.py download
    python scripts/summary_experiment.py run --gpu 0

Use --case-limit 1 for a short GPU smoke run. Download accesses the public Hugging Face checkpoint once. Inference then loads local-only weights, disables Qwen thinking mode, uses greedy generation, and blocks Hub access. Run files go to timestamped outputs/ directories under the data folder.

The synthetic set covers Korean/English notes, negation, uncertainty, patient versus family history, event time versus note-entry time, medication/dose, numeric units, explicitly unknown LKW, and conflicting onset times. Reported measures are JSON/schema validity, claim precision/recall/F1, exact quote support, exact event-time agreement, value agreement on aligned claims, and generation time. Review the Korean text manually too. This small synthetic set is not clinical validation.

## Model and runtime

The model is pinned to Qwen/Qwen3.5-9B revision c202236235762e1c871ad0ccb60c8ee5ba337b9a and its official Apache-2.0 license. The code was prepared against requirements-experiment.txt and the existing CUDA PyTorch 2.5.1 environment in jhbak_ct. It does not install or upgrade packages.

Only synthetic records are used. Do not put real patient data in Git or send it to hosted services. The prototype extracts source statements; it does not diagnose, recommend treatment, or determine tPA eligibility. A synthetic run does not establish clinical safety or readiness.
