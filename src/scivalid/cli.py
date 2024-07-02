"""SciValid command-line interface with stable exit codes."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .contract import load_contract
from .engine import validate
from .errors import ConfigurationError, ContractError, OptionalDependencyError, ReaderError
from .readers.registry import get_reader
from .reporters import render_terminal, write_html_report, write_json_report


EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_CONFIGURATION = 2
EXIT_OPERATIONAL = 3
EXIT_OPTIONAL_DEPENDENCY = 4


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scivalid", description="Validate scientific data against explicit contracts.")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="validate one or more files or directories")
    check.add_argument("paths", nargs="+")
    check.add_argument("--contract", required=True)
    check.add_argument("--format", dest="format_name")
    check.add_argument("--chunk-size", type=int, default=50_000)
    check.add_argument("--sample-limit", type=int)
    check.add_argument("--max-exact-values", type=int)
    check.add_argument("--fail-fast", action="store_true")
    check.add_argument("--strict", action="store_true", help="return exit 1 when warnings are present")
    check.add_argument("--report-json")
    check.add_argument("--report-html")
    check.add_argument("--max-terminal-findings", type=int, default=20)

    inspect = commands.add_parser("inspect", help="inspect file fields, dtypes, and shapes")
    inspect.add_argument("path")
    inspect.add_argument("--format", dest="format_name")

    contract = commands.add_parser("contract", help="contract utilities")
    contract_commands = contract.add_subparsers(dest="contract_command", required=True)
    contract_validate = contract_commands.add_parser("validate", help="parse and validate a contract")
    contract_validate.add_argument("path")

    compare = commands.add_parser("compare-schema", help="compare two file schemas")
    compare.add_argument("left")
    compare.add_argument("right")
    return parser


def _metadata_dict(path: str, format_name: Optional[str] = None) -> Dict[str, Any]:
    source = Path(path).absolute()
    reader_type = get_reader(source, format_name)
    with reader_type(source) as reader:
        metadata = reader.inspect_metadata()
    return {
        "path": str(metadata.path),
        "format": metadata.format,
        "reader": metadata.reader,
        "size_bytes": metadata.size_bytes,
        "row_count": metadata.row_count,
        "fields": {
            name: {"dtype": info.dtype, "shape": list(info.shape)}
            for name, info in sorted(metadata.fields.items())
        },
    }


def _run(args: argparse.Namespace) -> int:
    if args.command == "contract":
        parsed = load_contract(args.path)
        print("Contract is valid (version {}, dataset {!r}, hash {}).".format(
            parsed.contract_version, parsed.dataset, parsed.hash
        ))
        return EXIT_OK
    if args.command == "inspect":
        print(json.dumps(_metadata_dict(args.path, args.format_name), indent=2))
        return EXIT_OK
    if args.command == "compare-schema":
        left = _metadata_dict(args.left)
        right = _metadata_dict(args.right)
        left_schema = {name: (item["dtype"], item["shape"][1:]) for name, item in left["fields"].items()}
        right_schema = {name: (item["dtype"], item["shape"][1:]) for name, item in right["fields"].items()}
        result = {
            "equal": left_schema == right_schema,
            "only_left": sorted(set(left_schema) - set(right_schema)),
            "only_right": sorted(set(right_schema) - set(left_schema)),
            "changed": {
                name: {"left": left_schema[name], "right": right_schema[name]}
                for name in sorted(set(left_schema) & set(right_schema))
                if left_schema[name] != right_schema[name]
            },
        }
        print(json.dumps(result, indent=2))
        return EXIT_OK if result["equal"] else EXIT_FINDINGS

    report = validate(
        args.paths,
        args.contract,
        chunk_size=args.chunk_size,
        fail_fast=args.fail_fast,
        sample_limit=args.sample_limit,
        format_name=args.format_name,
        max_exact_values=args.max_exact_values,
    )
    report.metrics["strict"] = args.strict
    if args.report_json:
        write_json_report(report, args.report_json)
    if args.report_html:
        write_html_report(report, args.report_html)
    print(render_terminal(
        report,
        max_findings=args.max_terminal_findings,
        fail_on_warnings=args.strict,
    ))
    if report.metrics.get("optional_dependency_failed"):
        return EXIT_OPTIONAL_DEPENDENCY
    if not report.completed:
        return EXIT_OPERATIONAL
    if report.has_errors or (args.strict and report.has_warnings):
        return EXIT_FINDINGS
    return EXIT_OK


def main(argv: Optional[List[str]] = None) -> int:
    parser = _parser()
    try:
        return _run(parser.parse_args(argv))
    except (ContractError, ConfigurationError) as exc:
        print("Configuration error: {}".format(exc), file=sys.stderr)
        return EXIT_CONFIGURATION
    except OptionalDependencyError as exc:
        print("Optional dependency unavailable: {}".format(exc), file=sys.stderr)
        return EXIT_OPTIONAL_DEPENDENCY
    except (ReaderError, OSError) as exc:
        print("Operational error: {}".format(exc), file=sys.stderr)
        return EXIT_OPERATIONAL


if __name__ == "__main__":
    raise SystemExit(main())
