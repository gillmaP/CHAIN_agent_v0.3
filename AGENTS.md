# Shared development rules

- Team 1 owns `chain_agents/screening/` and `tests/test_screening.py`.
- Team 2 owns `chain_agents/summary/` and `tests/test_summary.py`.
- Team 3 owns `chain_agents/tpa/` and `tests/test_tpa.py`.
- Keep `invoke(request, snapshot, services) -> dict` as the public entrypoint.
- Implement domain logic in your team's `logic.py`; add helpers/prompts inside that team's directory.
- Preserve input provenance, versions, timestamps and status. Never mutate input objects.
- Return domain output only: upstream Runtime owns the Result envelope and all workflow state changes.
- Missing/unimplemented processing raises ValueError; do not return an error object as SUCCESS.
- Shared contracts/helpers or new output keys require review across teams and orchestration.
- Summary has one operation: build one complete question-oriented result per invocation. Do not add state-specific Summary paths.
- Orchestrator/API routing identifies the Agent. Do not duplicate agent/action selectors in the clinical request body.
- Synthetic mock output is not a clinical decision. Do not silently remove mock_only or invent confidence.
- Do not store credentials, real patient records or generated local runtime output in git.
- Run `python -m unittest discover -s tests -v` before proposing changes.
