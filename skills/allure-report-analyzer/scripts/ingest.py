"""Ingest Allure test results from allure-results JSON or generated HTML report data.

Usage:
    python ingest.py --input <dir|zip|html-report-dir> --output <dir>
    python ingest.py --input <path> --output <dir> --json-out <file>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

HIDDEN_STATUSES = frozenset({"skipped"})


def canonical_parameters(params: list[dict[str, Any]] | None) -> str:
    if not params:
        return ""
    pairs: list[tuple[str, str]] = []
    for p in params:
        name = str(p.get("name", ""))
        value = p.get("value")
        if isinstance(value, (dict, list)):
            value = json.dumps(value, sort_keys=True, ensure_ascii=False)
        else:
            value = str(value) if value is not None else ""
        pairs.append((name, value))
    pairs.sort(key=lambda x: x[0])
    return json.dumps(pairs, ensure_ascii=False)


def test_identity(data: dict[str, Any]) -> str:
    history_id = data.get("historyId")
    if history_id:
        return f"history:{history_id}"
    full_name = data.get("fullName") or data.get("name", "")
    params_key = canonical_parameters(data.get("parameters"))
    digest = hashlib.sha256(f"{full_name}\0{params_key}".encode()).hexdigest()[:16]
    return f"fullname:{full_name}\0{params_key}\0{digest}"


def normalize_result(data: dict[str, Any], source: str) -> dict[str, Any]:
    labels = {l["name"]: l["value"] for l in data.get("labels", []) if "name" in l and "value" in l}
    status_details = data.get("statusDetails") or {}
    message = status_details.get("message", "") or data.get("statusMessage", "")
    trace = status_details.get("trace", "") or data.get("statusTrace", "")

    return {
        "identity": test_identity(data),
        "historyId": data.get("historyId"),
        "uuid": data.get("uuid"),
        "name": data.get("name", ""),
        "fullName": data.get("fullName") or data.get("name", ""),
        "status": data.get("status", "unknown"),
        "parameters": data.get("parameters") or [],
        "labels": labels,
        "suite": labels.get("suite", ""),
        "parentSuite": labels.get("parentSuite", ""),
        "epic": labels.get("epic", ""),
        "feature": labels.get("feature", ""),
        "story": labels.get("story", ""),
        "message": str(message)[:500],
        "trace": str(trace)[:1000],
        "source": source,
        "hidden": data.get("hidden", False),
    }


def is_failed(status: str) -> bool:
    return status in ("failed", "broken")


def merge_results(existing: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """Keep last non-hidden result for the same identity (retries)."""
    if existing.get("hidden") and not new.get("hidden"):
        return new
    if not existing.get("hidden") and new.get("hidden"):
        return existing
    return new


def load_result_json_files(root: Path) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for file in root.rglob("*-result.json"):
        try:
            with open(file, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        norm = normalize_result(data, str(file.relative_to(root)))
        key = norm["identity"]
        if key in results:
            results[key] = merge_results(results[key], norm)
        else:
            results[key] = norm
    return results


def _widget_test_to_result(item: dict[str, Any], source: str) -> dict[str, Any]:
    status_details = item.get("statusDetails") or {}
    labels_list = item.get("labels") or []
    labels = (
        {l["name"]: l["value"] for l in labels_list if "name" in l and "value" in l}
        if labels_list
        else {}
    )
    data = {
        "uuid": item.get("uid") or item.get("uuid"),
        "historyId": item.get("historyId"),
        "name": item.get("name", ""),
        "fullName": item.get("fullName") or item.get("name", ""),
        "status": item.get("status", "unknown"),
        "parameters": item.get("parameters") or [],
        "labels": labels_list,
        "statusDetails": {
            "message": status_details.get("message", "") or item.get("statusMessage", ""),
            "trace": status_details.get("trace", "") or item.get("statusTrace", ""),
        },
        "hidden": item.get("hidden", False),
    }
    norm = normalize_result(data, source)
    return norm


def load_test_case_files(report_data_dir: Path) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    cases_dir = report_data_dir / "test-cases"
    if not cases_dir.is_dir():
        return results
    for file in cases_dir.glob("*.json"):
        try:
            with open(file, encoding="utf-8") as f:
                item = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(item, dict):
            continue
        norm = _widget_test_to_result(item, str(file.relative_to(report_data_dir)))
        key = norm["identity"]
        if key in results:
            results[key] = merge_results(results[key], norm)
        else:
            results[key] = norm
    return results


def load_suites_tree(report_data_dir: Path) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for name in ("suites.json", "packages.json"):
        path = report_data_dir / name
        if not path.is_file():
            continue
        try:
            with open(path, encoding="utf-8") as f:
                tree = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        _walk_suite_tree(tree, results, report_data_dir)
    return results


def _walk_suite_tree(node: Any, results: dict[str, dict[str, Any]], base: Path) -> None:
    if isinstance(node, list):
        for item in node:
            _walk_suite_tree(item, results, base)
        return
    if not isinstance(node, dict):
        return

    children = node.get("children") or []
    for child in children:
        _walk_suite_tree(child, results, base)

    for test in node.get("testCases") or node.get("tests") or []:
        if not isinstance(test, dict):
            continue
        norm = _widget_test_to_result(test, "suites-tree")
        key = norm["identity"]
        if key in results:
            results[key] = merge_results(results[key], norm)
        else:
            results[key] = norm


def find_report_data_dir(root: Path) -> Path | None:
    if (root / "data" / "test-cases").is_dir():
        return root / "data"
    if (root / "test-cases").is_dir():
        return root
    for candidate in root.rglob("data"):
        if candidate.is_dir() and (candidate / "test-cases").is_dir():
            return candidate
    return None


def load_html_report(root: Path) -> dict[str, dict[str, Any]]:
    data_dir = find_report_data_dir(root)
    if not data_dir:
        return {}
    results = load_test_case_files(data_dir)
    tree_results = load_suites_tree(data_dir)
    for key, value in tree_results.items():
        if key in results:
            results[key] = merge_results(results[key], value)
        else:
            results[key] = value
    return results


def extract_zip(zip_path: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(dest)
    return dest


def ingest_path(input_path: Path) -> dict[str, dict[str, Any]]:
    if not input_path.exists():
        print(f"ERROR: Input not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    if input_path.is_file() and input_path.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            extract_zip(input_path, tmp_path)
            return ingest_directory(tmp_path)

    if input_path.is_dir():
        return ingest_directory(input_path)

    print(f"ERROR: Unsupported input: {input_path}", file=sys.stderr)
    sys.exit(1)


def ingest_directory(root: Path) -> dict[str, dict[str, Any]]:
    json_results = load_result_json_files(root)
    if json_results:
        return json_results

    html_results = load_html_report(root)
    if html_results:
        return html_results

    print(
        "ERROR: No parseable Allure data found. Expected *-result.json (allure-results) "
        "or generated report data/test-cases/*.json",
        file=sys.stderr,
    )
    sys.exit(1)


def write_output(results: dict[str, dict[str, Any]], output_dir: Path, json_out: Path | None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "count": len(results),
        "tests": list(results.values()),
    }
    manifest_path = output_dir / "ingested.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"Ingested {len(results)} test cases -> {manifest_path}")


def suite_health_summary(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    from collections import Counter

    stats = Counter()
    message_prefixes = Counter()
    for t in results.values():
        stats[t["status"]] += 1
        if is_failed(t["status"]) and t.get("message"):
            prefix = t["message"].split("\n")[0][:120]
            message_prefixes[prefix] += 1

    total = len(results)
    passed = stats.get("passed", 0)
    failed = stats.get("failed", 0)
    broken = stats.get("broken", 0)
    skipped = stats.get("skipped", 0)
    executed = total - skipped

    red_flags: list[dict[str, str]] = []

    if total == 0:
        red_flags.append({"flag": "Empty or truncated results", "evidence": "Zero tests ingested"})
    elif failed + broken > passed:
        red_flags.append(
            {
                "flag": "Majority red",
                "evidence": f"failed+broken ({failed + broken}) > passed ({passed})",
            }
        )
    if total > 0 and passed == 0:
        red_flags.append({"flag": "No passes", "evidence": f"passed == 0 of {total} total"})
    if total > 0 and skipped > total * 0.5:
        red_flags.append(
            {
                "flag": "Extreme skip rate",
                "evidence": f"skipped {skipped} ({100 * skipped / total:.1f}% of total)",
            }
        )
    if total > 0 and broken > total * 0.15:
        red_flags.append(
            {
                "flag": "Harness collapse",
                "evidence": f"broken {broken} ({100 * broken / total:.1f}% of total)",
            }
        )
    elif failed > 0 and broken > failed:
        red_flags.append(
            {
                "flag": "Harness collapse",
                "evidence": f"broken ({broken}) > failed ({failed})",
            }
        )
    if message_prefixes and failed + broken > 0:
        top_prefix, top_count = message_prefixes.most_common(1)[0]
        if top_count > (failed + broken) * 0.25:
            red_flags.append(
                {
                    "flag": "Dominant infra/fixture failure",
                    "evidence": f'"{top_prefix}" accounts for {top_count} of {failed + broken} failures',
                }
            )

    return {
        "counts": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "broken": broken,
            "skipped": skipped,
            "executed": executed,
        },
        "rates": {
            "passed_pct": round(100 * passed / total, 1) if total else 0,
            "failed_pct": round(100 * failed / total, 1) if total else 0,
            "broken_pct": round(100 * broken / total, 1) if total else 0,
            "skipped_pct": round(100 * skipped / total, 1) if total else 0,
            "red_pct_executed": round(100 * (failed + broken) / executed, 1) if executed else 0,
        },
        "top_failure_patterns": [
            {"count": c, "pattern": p} for p, c in message_prefixes.most_common(15)
        ],
        "red_flags": red_flags,
        "red_flag_count": len(red_flags),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Allure test results")
    parser.add_argument("--input", required=True, help="Directory, zip, or HTML report root")
    parser.add_argument("--output", required=True, help="Output directory for ingested.json")
    parser.add_argument("--json-out", default=None, help="Optional additional JSON output path")
    parser.add_argument("--health-summary", action="store_true", help="Print suite health JSON to stdout")
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_dir = Path(args.output).expanduser().resolve()
    json_out = Path(args.json_out).expanduser().resolve() if args.json_out else None

    results = ingest_path(input_path)
    write_output(results, output_dir, json_out)

    if args.health_summary:
        summary = suite_health_summary(results)
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
