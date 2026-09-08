"""Identity-safe comparison of two ingested Allure result sets.

Usage:
    python compare.py --baseline <dir> --target <dir> [--output <file>]

Each directory should contain ingested.json (from ingest.py) or raw *-result.json files.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from ingest import ingest_directory, is_failed


def load_results(path: Path) -> dict[str, dict]:
    ingested = path / "ingested.json"
    if ingested.is_file():
        with open(ingested, encoding="utf-8") as f:
            data = json.load(f)
        tests = data.get("tests") or []
        return {t["identity"]: t for t in tests if t.get("identity")}

    if path.is_dir():
        return ingest_directory(path)

    print(f"ERROR: Cannot load results from {path}", file=sys.stderr)
    sys.exit(1)


def compare_results(baseline: dict[str, dict], target: dict[str, dict]) -> dict:
    all_ids = set(baseline.keys()) | set(target.keys())

    new_failures: list[dict] = []
    fixed_tests: list[dict] = []
    persistent_failures: list[dict] = []
    new_tests_failed: list[dict] = []
    new_tests_passed: list[dict] = []

    baseline_stats: dict[str, int] = defaultdict(int)
    target_stats: dict[str, int] = defaultdict(int)

    for t in baseline.values():
        baseline_stats[t["status"]] += 1
    for t in target.values():
        target_stats[t["status"]] += 1

    for test_id in all_ids:
        b = baseline.get(test_id)
        t = target.get(test_id)

        if b is None and t is not None:
            if is_failed(t["status"]):
                new_tests_failed.append(t)
                new_failures.append(
                    {
                        "test": t,
                        "baseline_status": "absent",
                        "target_status": t["status"],
                        "branch_only": True,
                    }
                )
            else:
                new_tests_passed.append(t)
            continue

        if t is None and b is not None:
            continue

        assert b is not None and t is not None

        b_failed = is_failed(b["status"])
        t_failed = is_failed(t["status"])

        if not b_failed and t_failed:
            new_failures.append(
                {
                    "test": t,
                    "baseline_status": b["status"],
                    "target_status": t["status"],
                    "branch_only": False,
                }
            )
        elif b_failed and t["status"] == "passed":
            fixed_tests.append(
                {
                    "test": t,
                    "baseline_status": b["status"],
                    "target_status": t["status"],
                    "baseline_message": b.get("message", ""),
                }
            )
        elif b_failed and t_failed:
            persistent_failures.append(
                {
                    "test": t,
                    "baseline_status": b["status"],
                    "target_status": t["status"],
                    "baseline_message": b.get("message", ""),
                    "target_message": t.get("message", ""),
                }
            )

    return {
        "summary": {
            "baseline": {
                "total": len(baseline),
                "passed": baseline_stats.get("passed", 0),
                "failed": baseline_stats.get("failed", 0),
                "broken": baseline_stats.get("broken", 0),
                "skipped": baseline_stats.get("skipped", 0),
            },
            "target": {
                "total": len(target),
                "passed": target_stats.get("passed", 0),
                "failed": target_stats.get("failed", 0),
                "broken": target_stats.get("broken", 0),
                "skipped": target_stats.get("skipped", 0),
            },
        },
        "new_failures": sorted(new_failures, key=lambda x: x["test"]["fullName"]),
        "fixed_tests": sorted(fixed_tests, key=lambda x: x["test"]["fullName"]),
        "persistent_failures": sorted(persistent_failures, key=lambda x: x["test"]["fullName"]),
        "new_tests_failed": sorted(new_tests_failed, key=lambda x: x["fullName"]),
        "new_tests_passed": sorted(new_tests_passed, key=lambda x: x["fullName"]),
        "counts": {
            "new_failures": len(new_failures),
            "fixed": len(fixed_tests),
            "persistent_failures": len(persistent_failures),
            "new_tests_failed": len(new_tests_failed),
            "new_tests_passed": len(new_tests_passed),
            "regressions_introduced": len(new_failures),
        },
    }


def print_summary(report: dict) -> None:
    s = report["summary"]
    c = report["counts"]

    print("=" * 70)
    print("ALLURE COMPARISON REPORT")
    print("=" * 70)
    print(f"\n{'Metric':<25} {'Baseline':<20} {'Target':<20}")
    print("-" * 65)
    print(f"{'Total tests':<25} {s['baseline']['total']:<20} {s['target']['total']:<20}")
    print(f"{'Passed':<25} {s['baseline']['passed']:<20} {s['target']['passed']:<20}")
    print(f"{'Failed':<25} {s['baseline']['failed']:<20} {s['target']['failed']:<20}")
    print(f"{'Broken':<25} {s['baseline']['broken']:<20} {s['target']['broken']:<20}")
    print(f"{'Skipped':<25} {s['baseline']['skipped']:<20} {s['target']['skipped']:<20}")

    print(f"\n{'Category':<30} {'Count':<10}")
    print("-" * 40)
    print(f"{'Regressions introduced':<30} {c['regressions_introduced']:<10}")
    print(f"{'  (regression failures)':<30} {c['new_failures'] - c['new_tests_failed']:<10}")
    print(f"{'  (new tests failed)':<30} {c['new_tests_failed']:<10}")
    print(f"{'Fixed tests (failed->passed)':<30} {c['fixed']:<10}")
    print(f"{'Persistent failures':<30} {c['persistent_failures']:<10}")
    print(f"{'New tests (passed)':<30} {c['new_tests_passed']:<10}")

    verdict = "APPROVE" if c["regressions_introduced"] == 0 else "DISAPPROVE"
    print(f"\nDelta verdict: {verdict}")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two Allure result sets")
    parser.add_argument("--baseline", required=True, help="Baseline results directory")
    parser.add_argument("--target", required=True, help="Target results directory")
    parser.add_argument("--output", default=None, help="JSON output path")
    args = parser.parse_args()

    baseline_path = Path(args.baseline).expanduser().resolve()
    target_path = Path(args.target).expanduser().resolve()

    print(f"Loading baseline from: {baseline_path}")
    baseline = load_results(baseline_path)
    print(f"  Found {len(baseline)} test cases")

    print(f"Loading target from: {target_path}")
    target = load_results(target_path)
    print(f"  Found {len(target)} test cases")

    if not baseline:
        print("ERROR: No test results in baseline", file=sys.stderr)
        sys.exit(1)
    if not target:
        print("ERROR: No test results in target", file=sys.stderr)
        sys.exit(1)

    report = compare_results(baseline, target)
    print_summary(report)

    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nFull report written to: {out}")


if __name__ == "__main__":
    main()
