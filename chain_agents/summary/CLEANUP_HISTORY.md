# Summary prototype cleanup — 2026-10-08

The accepted version is the reviewed S1 single-call prototype. No inference, prompt, GT, model or scoring changes were made during cleanup.

Full pre-cleanup source backup: `/data/data2/jhbak/CHAIN_agent_summary_prototype/archives/s1_frozen_20261008/source_before_cleanup.tar.gz`. SHA256 manifest and Git status are alongside it. Deleted source remains recoverable there, outside the active repository.

| Removed path | Previous role / reason |
|---|---|
| `chain_agents/summary/FIELDS_SCHEMA.md` | Superseded broad-field schema and runners |
| `chain_agents/summary/fields_cases.py` | Superseded broad-field schema and runners |
| `chain_agents/summary/fields_experiment.py` | Superseded broad-field schema and runners |
| `chain_agents/summary/fields_report.py` | Superseded broad-field schema and runners |
| `chain_agents/summary/fields_schema.py` | Superseded broad-field schema and runners |
| `chain_agents/summary/architecture_comparison.py` | Superseded broad-field schema and runners |
| `chain_agents/summary/replay_adapter_v2.py` | Superseded broad-field schema and runners |
| `chain_agents/summary/HISTORY_SUMMARY.md` | Superseded assertion-based history extraction and reports |
| `chain_agents/summary/history_summary.py` | Superseded assertion-based history extraction and reports |
| `chain_agents/summary/history_extractor.py` | Superseded assertion-based history extraction and reports |
| `chain_agents/summary/run_history.py` | Superseded assertion-based history extraction and reports |
| `chain_agents/summary/history_benchmark_report.py` | Superseded assertion-based history extraction and reports |
| `chain_agents/summary/history_stress_run.py` | Superseded assertion-based history extraction and reports |
| `chain_agents/summary/history_stress_report.py` | Superseded assertion-based history extraction and reports |
| `chain_agents/summary/history_quote_first.py` | Superseded assertion-based history extraction and reports |
| `chain_agents/summary/history_quote_first_report.py` | Superseded assertion-based history extraction and reports |
| `chain_agents/summary/PROTOTYPE.md` | Superseded output-contract documentation |
| `chain_agents/summary/OUTPUT_SCHEMA.md` | Superseded output-contract documentation |
| `tests/test_summary_fields.py` | Tests of retired field/assertion contracts; current S1 rule tests retained and made discoverable. |
| `tests/test_summary_history.py` | Tests of retired field/assertion contracts; current S1 rule tests retained and made discoverable. |
| `tests/test_summary_history_stress.py` | Tests of retired field/assertion contracts; current S1 rule tests retained and made discoverable. |

Retained active dependencies: `experiment.py`, `history_stress_cases.py`, `mock_contract.py`, all `history_s1_*` modules, original public entrypoint and v0.3 compatibility. Existing raw results, model weights, runtime, source reference archive and HTML reports were not deleted.

## Local working-copy cleanup

Backup: `/data/data2/jhbak/CHAIN_agent_summary_prototype/archives/s1_frozen_20261008/local_retired_sources.zip`

- `fields_cases.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `fields_experiment.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `fields_report.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `FIELDS_SCHEMA.md`: retired experiment copy or one-off inspection of the previous order experiment.
- `fields_schema.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `test_summary_fields.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `summary_mock_impl\audit_s1_order_results.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `summary_mock_impl\history_benchmark_report.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `summary_mock_impl\history_extractor.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `summary_mock_impl\history_quote_first.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `summary_mock_impl\history_quote_first_report.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `summary_mock_impl\history_stress_report.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `summary_mock_impl\history_stress_run.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `summary_mock_impl\HISTORY_SUMMARY.md`: retired experiment copy or one-off inspection of the previous order experiment.
- `summary_mock_impl\history_summary.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `summary_mock_impl\inspect_s1_order_results.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `summary_mock_impl\run_history.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `summary_mock_impl\test_summary_history.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `summary_mock_impl\test_summary_history_stress.py`: retired experiment copy or one-off inspection of the previous order experiment.
- `summary_mock_impl\verify_s1_order.py`: retired experiment copy or one-off inspection of the previous order experiment.
