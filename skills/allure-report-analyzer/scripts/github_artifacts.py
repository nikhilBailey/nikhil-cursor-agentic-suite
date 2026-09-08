"""Download Allure artifacts from GitHub Actions and infer baseline runs.

Usage:
    python github_artifacts.py download --run <id> --repo <owner/repo> --output <dir>
    python github_artifacts.py download-url --url <artifact-url> --output <dir>
    python github_artifacts.py infer-baseline --run <target_id> --repo <owner/repo> --output <dir>
    python github_artifacts.py run-info --run <id> --repo <owner/repo>
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from ingest import extract_zip, ingest_path, write_output


def run_gh(args: list[str], check: bool = True) -> str:
    cmd = ["gh"] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=check)
    except FileNotFoundError:
        print("ERROR: 'gh' CLI not found. Install and run 'gh auth login'.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: gh command failed: {' '.join(cmd)}", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def parse_repo(repo: str | None) -> str:
    if repo:
        return repo
    try:
        url = run_gh(["remote", "get-url", "origin"], check=False)
    except SystemExit:
        url = ""
    if not url:
        print("ERROR: --repo required (could not detect from git remote)", file=sys.stderr)
        sys.exit(1)
    url = url.strip()
    if url.startswith("git@"):
        # git@github.com:owner/repo.git
        match = re.search(r"[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    else:
        match = re.search(r"github\.com[:/]([^/]+/[^/]+?)(?:\.git)?", url)
    if not match:
        print(f"ERROR: Could not parse repo from remote: {url}", file=sys.stderr)
        sys.exit(1)
    return match.group(1)


def parse_artifact_url(url: str) -> tuple[str, int, int]:
    """Return (repo, run_id, artifact_id)."""
    parsed = urlparse(url)
    path = parsed.path
    # /owner/repo/actions/runs/123/artifacts/456
    match = re.search(r"/([^/]+/[^/]+)/actions/runs/(\d+)/artifacts/(\d+)", path)
    if not match:
        print(f"ERROR: Cannot parse artifact URL: {url}", file=sys.stderr)
        sys.exit(1)
    return match.group(1), int(match.group(2)), int(match.group(3))


def rank_artifact_names(names: list[str]) -> list[str]:
    def score(name: str) -> tuple[int, str]:
        lower = name.lower()
        if "allure-results" in lower:
            return (0, lower)
        if "allure" in lower:
            return (1, lower)
        return (2, lower)

    return sorted(names, key=score)


def list_artifacts(repo: str, run_id: int) -> list[dict]:
    raw = run_gh(
        [
            "run",
            "view",
            str(run_id),
            "--repo",
            repo,
            "--json",
            "artifacts,workflowName,headBranch,conclusion,status,displayTitle,url",
        ]
    )
    data = json.loads(raw)
    artifacts = data.get("artifacts") or []
    return artifacts


def pick_artifact_name(artifacts: list[dict]) -> str:
    names = [a["name"] for a in artifacts if a.get("name")]
    if not names:
        print("ERROR: No artifacts on this run", file=sys.stderr)
        sys.exit(1)
    ranked = rank_artifact_names(names)
    return ranked[0]


def download_artifact(repo: str, run_id: int, artifact_name: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    download_dir = output_dir / "_download"
    if download_dir.exists():
        shutil.rmtree(download_dir)
    download_dir.mkdir(parents=True)

    run_gh(
        [
            "run",
            "download",
            str(run_id),
            "--repo",
            repo,
            "--name",
            artifact_name,
            "--dir",
            str(download_dir),
        ]
    )
    return download_dir


def ingest_download_dir(download_dir: Path, output_dir: Path) -> None:
    zips = list(download_dir.rglob("*.zip"))
    if zips:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            extract_zip(zips[0], tmp_path)
            results = ingest_path(tmp_path)
    else:
        results = ingest_path(download_dir)
    write_output(results, output_dir, None)


def cmd_download(args: argparse.Namespace) -> None:
    repo = parse_repo(args.repo)
    output_dir = Path(args.output).expanduser().resolve()
    artifacts = list_artifacts(repo, args.run)
    name = args.artifact or pick_artifact_name(artifacts)
    print(f"Downloading artifact '{name}' from run {args.run} ({repo})")
    download_dir = download_artifact(repo, args.run, name, output_dir)
    ingest_download_dir(download_dir, output_dir)
    shutil.rmtree(output_dir / "_download", ignore_errors=True)


def cmd_download_url(args: argparse.Namespace) -> None:
    repo, run_id, _artifact_id = parse_artifact_url(args.url)
    output_dir = Path(args.output).expanduser().resolve()
    artifacts = list_artifacts(repo, run_id)
    name = pick_artifact_name(artifacts)
    print(f"Downloading artifact '{name}' from {args.url}")
    download_dir = download_artifact(repo, run_id, name, output_dir)
    ingest_download_dir(download_dir, output_dir)
    shutil.rmtree(output_dir / "_download", ignore_errors=True)


def cmd_run_info(args: argparse.Namespace) -> None:
    repo = parse_repo(args.repo)
    raw = run_gh(
        [
            "run",
            "view",
            str(args.run),
            "--repo",
            repo,
            "--json",
            "databaseId,workflowName,headBranch,conclusion,status,displayTitle,url,createdAt,event",
        ]
    )
    print(raw)


def get_default_branch(repo: str) -> str:
    raw = run_gh(["repo", "view", repo, "--json", "defaultBranchRef"])
    data = json.loads(raw)
    ref = data.get("defaultBranchRef") or {}
    name = ref.get("name")
    if not name:
        print(f"ERROR: Could not determine default branch for {repo}", file=sys.stderr)
        sys.exit(1)
    return name


def cmd_infer_baseline(args: argparse.Namespace) -> None:
    repo = parse_repo(args.repo)
    output_dir = Path(args.output).expanduser().resolve()

    target_info = json.loads(
        run_gh(
            [
                "run",
                "view",
                str(args.run),
                "--repo",
                repo,
                "--json",
                "workflowName,headBranch,createdAt",
            ]
        )
    )
    workflow = target_info.get("workflowName")
    if not workflow:
        print("ERROR: Could not determine workflow name for target run", file=sys.stderr)
        sys.exit(1)

    default_branch = get_default_branch(repo)
    print(f"Inferring baseline: workflow={workflow}, branch={default_branch}")

    runs_raw = run_gh(
        [
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            workflow,
            "--branch",
            default_branch,
            "--limit",
            "30",
            "--json",
            "databaseId,conclusion,createdAt,headBranch",
        ]
    )
    runs = json.loads(runs_raw)
    baseline_id = None
    for run in runs:
        rid = run.get("databaseId")
        if rid and rid != args.run and run.get("conclusion") in ("success", "failure"):
            baseline_id = rid
            break

    if not baseline_id:
        print("ERROR: Could not find a baseline run on default branch", file=sys.stderr)
        sys.exit(1)

    print(f"Inferred baseline run: {baseline_id} (inferred)")
    meta_path = output_dir.parent / "baseline-meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "baseline_run_id": baseline_id,
                "target_run_id": args.run,
                "workflow": workflow,
                "default_branch": default_branch,
                "inferred": True,
            },
            f,
            indent=2,
        )

    artifacts = list_artifacts(repo, baseline_id)
    name = pick_artifact_name(artifacts)
    download_dir = download_artifact(repo, baseline_id, name, output_dir)
    ingest_download_dir(download_dir, output_dir)
    shutil.rmtree(output_dir / "_download", ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="GitHub Actions Allure artifact helpers")
    sub = parser.add_subparsers(dest="command", required=True)

    p_dl = sub.add_parser("download", help="Download Allure artifact from a run")
    p_dl.add_argument("--run", type=int, required=True)
    p_dl.add_argument("--repo", default=None)
    p_dl.add_argument("--artifact", default=None, help="Artifact name (auto-detected if omitted)")
    p_dl.add_argument("--output", required=True)
    p_dl.set_defaults(func=cmd_download)

    p_url = sub.add_parser("download-url", help="Download from artifact URL")
    p_url.add_argument("--url", required=True)
    p_url.add_argument("--output", required=True)
    p_url.set_defaults(func=cmd_download_url)

    p_inf = sub.add_parser("infer-baseline", help="Infer and download baseline from default branch")
    p_inf.add_argument("--run", type=int, required=True)
    p_inf.add_argument("--repo", default=None)
    p_inf.add_argument("--output", required=True)
    p_inf.set_defaults(func=cmd_infer_baseline)

    p_info = sub.add_parser("run-info", help="Print run metadata as JSON")
    p_info.add_argument("--run", type=int, required=True)
    p_info.add_argument("--repo", default=None)
    p_info.set_defaults(func=cmd_run_info)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
