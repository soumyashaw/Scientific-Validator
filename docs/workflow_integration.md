# Workflow integration

Use validation as the first task and allow downstream work only after exit 0.

```bash
scivalid check data/ --contract contract.yaml --report-json artifacts/report.json
python analysis.py  # reached only if the shell or workflow honors the exit code
```

`examples/workflow_gate.py` implements the same pattern through the Python API.
BatchFlow or another DAG engine can wrap `validation_gate` as a task and declare
the analysis task dependent on it. The gate raises on ERROR findings or an
incomplete report and keeps the JSON artifact for provenance.

Warnings do not block the task unless policy invokes the CLI with `--strict` or
checks `report.has_warnings` in the Python wrapper.

