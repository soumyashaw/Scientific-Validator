"""Executable validation gate suitable for a workflow task wrapper."""

from pathlib import Path

from scivalid import validate
from scivalid.reporters.json_report import write_json_report


def validation_gate(data: Path, contract: Path, report_path: Path):
    report = validate([data], contract)
    write_json_report(report, report_path)
    if not report.completed:
        raise RuntimeError("Validation did not complete; inspect {}".format(report_path))
    if report.has_errors:
        raise RuntimeError("Dataset contract failed; inspect {}".format(report_path))
    return report_path


def downstream_analysis(data: Path) -> None:
    print("Validated input is ready for analysis: {}".format(data))


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    data_path = root / "particle_events" / "valid"
    contract_path = root / "particle_events" / "contract.yaml"
    artifact = root.parent / "build" / "workflow-validation.json"
    validation_gate(data_path, contract_path, artifact)
    downstream_analysis(data_path)

