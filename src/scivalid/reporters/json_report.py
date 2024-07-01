"""Versioned machine-readable JSON report writer."""

import json
from pathlib import Path
from typing import Union

from ..models import Report


def write_json_report(report: Report, destination: Union[str, Path]) -> None:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=False, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

