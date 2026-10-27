#!/usr/bin/env python3
"""Discover workplace adapter.json files and install user or project symlinks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


class AdapterError(Exception):
    pass


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def discover_adapters(workplace_dir: Path) -> list[tuple[str, Path, dict[str, Any]]]:
    if not workplace_dir.is_dir():
        return []
    out: list[tuple[str, Path, dict[str, Any]]] = []
    for wp_dir in sorted(workplace_dir.iterdir()):
        if not wp_dir.is_dir():
            continue
        adapter_path = wp_dir / "adapter.json"
        if not adapter_path.is_file():
            continue
        try:
            data = json.loads(adapter_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise AdapterError(f"{adapter_path}: {exc}") from exc
        if not isinstance(data, dict):
            raise AdapterError(f"{adapter_path}: root must be a JSON object")
        out.append((wp_dir.name, adapter_path, data))
    return out


def resolve_root(adapter_dir: Path, data: dict[str, Any]) -> Path:
    raw = data.get("root")
    if raw is None or raw == "":
        return adapter_dir.resolve()
    path = Path(str(raw))
    if not path.is_absolute():
        path = (adapter_dir / path).resolve()
    else:
        path = path.resolve()
    if not path.is_dir():
        raise AdapterError(f"adapter root not found: {path}")
    return path


def _glob_patterns(section: dict[str, Any], key: str) -> list[str]:
    value = section.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise AdapterError(f"{key} must be a list of glob strings")
    return [str(p).strip() for p in value if str(p).strip()]


def expand_skill_dirs(root: Path, patterns: list[str]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for pattern in patterns:
        clean = pattern.rstrip("/")
        for candidate in root.glob(clean):
            if candidate.is_dir() and (candidate / "SKILL.md").is_file():
                name = candidate.name
                if name in found and found[name].resolve() != candidate.resolve():
                    raise AdapterError(
                        f"skill name collision under {root}: {name} "
                        f"({found[name]} vs {candidate})"
                    )
                found[name] = candidate.resolve()
    return found


def expand_agent_files(root: Path, patterns: list[str]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for pattern in patterns:
        for candidate in root.glob(pattern):
            if not candidate.is_file():
                continue
            name = candidate.stem
            if name in found and found[name].resolve() != candidate.resolve():
                raise AdapterError(
                    f"agent name collision under {root}: {name} "
                    f"({found[name]} vs {candidate})"
                )
            found[name] = candidate.resolve()
    return found


def expand_files(root: Path, patterns: list[str]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for pattern in patterns:
        for candidate in root.glob(pattern):
            if not candidate.is_file():
                continue
            name = candidate.name
            if name in found and found[name].resolve() != candidate.resolve():
                raise AdapterError(
                    f"file name collision under {root}: {name} "
                    f"({found[name]} vs {candidate})"
                )
            found[name] = candidate.resolve()
    return found


def legacy_flat_skills(workplace_dir: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for wp_child in workplace_dir.iterdir():
        if not wp_child.is_dir():
            continue
        for skill_dir in wp_child.iterdir():
            if not skill_dir.is_dir():
                continue
            if not (skill_dir / "SKILL.md").is_file():
                continue
            name = skill_dir.name
            resolved = skill_dir.resolve()
            if name in found and found[name] != resolved:
                raise AdapterError(f"legacy skill name collision: {name}")
            found[name] = resolved
    return found


def collect_first_party_paths(
    workplace_dir: Path, adapters: list[tuple[str, Path, dict[str, Any]]]
) -> list[tuple[str, Path]]:
    sources: list[tuple[str, Path]] = []
    for wp_id, adapter_path, data in adapters:
        hooks = data.get("hooks")
        if isinstance(hooks, dict):
            fp = hooks.get("firstParty")
            if fp:
                p = Path(str(fp))
                if not p.is_absolute():
                    p = (adapter_path.parent / p).resolve()
                else:
                    p = p.resolve()
                if not p.is_file():
                    raise AdapterError(f"{adapter_path}: hooks.firstParty not found: {p}")
                sources.append((wp_id, p))
    for policy in workplace_dir.glob("*/hooks/first-party.json"):
        wp_id = policy.parent.parent.name
        sources.append((wp_id, policy.resolve()))
    by_path: dict[Path, str] = {}
    for wp_id, path in sources:
        by_path[path] = wp_id
    if len(by_path) > 1:
        detail = ", ".join(f"{wp} ({p})" for p, wp in by_path.items())
        raise AdapterError(
            f"multiple workplaces supply first-party.json; keep one: {detail}"
        )
    return [(by_path[p], p) for p in by_path]


def _install_symlink(link_path: Path, target: Path, label: str) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    target = target.resolve()
    if link_path.is_symlink():
        existing = Path(os.readlink(link_path))
        if not existing.is_absolute():
            existing = (link_path.parent / existing).resolve()
        else:
            existing = existing.resolve()
        if existing == target:
            return
    if link_path.exists() or link_path.is_symlink():
        raise AdapterError(
            f"{label}: refusing to overwrite {link_path} (wanted symlink to {target})"
        )
    link_path.symlink_to(target)


def merge_maps(
    dest_label: str,
    accumulated: dict[str, tuple[str, Path]],
    wp_id: str,
    new_map: dict[str, Path],
) -> None:
    for name, target in new_map.items():
        if name in accumulated:
            prev_wp, prev_target = accumulated[name]
            if prev_target.resolve() != target.resolve():
                raise AdapterError(
                    f"{dest_label} name collision for '{name}': "
                    f"{prev_wp} ({prev_target}) vs {wp_id} ({target})"
                )
            continue
        accumulated[name] = (wp_id, target)


def _conflicts_with_committed_dir(link: Path, kind: str, name: str) -> None:
    if link.exists() and not link.is_symlink():
        raise AdapterError(f"{kind} '{name}' conflicts with committed path at {link}")


def restore_user(cursor_home: Path, workplace_dir: Path) -> None:
    adapters = discover_adapters(workplace_dir)
    skills_dest = cursor_home / "skills"
    agents_dest = cursor_home / "agents"
    skills_dest.mkdir(parents=True, exist_ok=True)
    agents_dest.mkdir(parents=True, exist_ok=True)

    skill_links: dict[str, tuple[str, Path]] = {}
    agent_links: dict[str, tuple[str, Path]] = {}

    merge_maps("user skill", skill_links, "legacy", legacy_flat_skills(workplace_dir))

    for wp_id, adapter_path, data in adapters:
        root = resolve_root(adapter_path.parent, data)
        user = data.get("user")
        if not isinstance(user, dict):
            user = {}
        merge_maps(
            "user skill",
            skill_links,
            wp_id,
            expand_skill_dirs(root, _glob_patterns(user, "skillGlobs")),
        )
        merge_maps(
            "user agent",
            agent_links,
            wp_id,
            expand_agent_files(root, _glob_patterns(user, "agentGlobs")),
        )

    for name, (_wp, target) in skill_links.items():
        link = skills_dest / name
        _conflicts_with_committed_dir(link, "user skill", name)
        _install_symlink(link, target, f"user skill {name}")

    for name, (_wp, target) in agent_links.items():
        link_md = agents_dest / f"{name}.md"
        _conflicts_with_committed_dir(link_md, "user agent", name)
        _install_symlink(link_md, target, f"user agent {name}")

    first_party = collect_first_party_paths(workplace_dir, adapters)
    if first_party:
        wp_id, src = first_party[0]
        hooks_dest = cursor_home / "hooks"
        hooks_dest.mkdir(parents=True, exist_ok=True)
        dest = hooks_dest / "first-party.json"
        dest.write_bytes(src.read_bytes())
        print(f"workplace-adapters: installed first-party policy from {wp_id}")


def link_project(repo_root: Path, project_path: Path, workplace_dir: Path) -> None:
    project_path = project_path.resolve()
    suite_root = repo_root.resolve()
    if project_path == suite_root:
        raise AdapterError("refusing to link project adapters into the suite repo")

    adapters = discover_adapters(workplace_dir)
    cursor_dir = project_path / ".cursor"
    skills_dest = cursor_dir / "skills"
    agents_dest = cursor_dir / "agents"
    refs_dest = cursor_dir / "references"
    rules_dest = cursor_dir / "rules"

    skill_links: dict[str, tuple[str, Path]] = {}
    agent_links: dict[str, tuple[str, Path]] = {}
    ref_links: dict[str, tuple[str, Path]] = {}
    rule_links: dict[str, tuple[str, Path]] = {}

    for wp_id, adapter_path, data in adapters:
        root = resolve_root(adapter_path.parent, data)
        project = data.get("project")
        if not isinstance(project, dict):
            continue
        merge_maps(
            "project skill",
            skill_links,
            wp_id,
            expand_skill_dirs(root, _glob_patterns(project, "skillGlobs")),
        )
        merge_maps(
            "project agent",
            agent_links,
            wp_id,
            expand_agent_files(root, _glob_patterns(project, "agentGlobs")),
        )
        merge_maps(
            "project reference",
            ref_links,
            wp_id,
            expand_files(root, _glob_patterns(project, "referenceGlobs")),
        )
        merge_maps(
            "project rule",
            rule_links,
            wp_id,
            expand_files(root, _glob_patterns(project, "ruleGlobs")),
        )

    for name, (_wp, target) in skill_links.items():
        _install_symlink(skills_dest / name, target, f"project skill {name}")

    for name, (_wp, target) in agent_links.items():
        _install_symlink(agents_dest / f"{name}.md", target, f"project agent {name}")

    for name, (_wp, target) in ref_links.items():
        _install_symlink(refs_dest / name, target, f"project reference {name}")

    for name, (_wp, target) in rule_links.items():
        _install_symlink(rules_dest / name, target, f"project rule {name}")

    print(f"workplace-adapters: linked project overlays under {cursor_dir}")


def _under_workplace_specific(path: Path, repo_root: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return True
    workplace = (repo_root / "workplace-specific").resolve()
    return workplace in resolved.parents or resolved == workplace


def backup_exclude_names(cursor_subdir: Path, repo_root: Path, skills_only_symlinks: bool) -> list[str]:
    if not cursor_subdir.is_dir():
        return []
    names: list[str] = []
    for entry in cursor_subdir.iterdir():
        if entry.is_symlink():
            names.append(entry.name)
            continue
        if skills_only_symlinks:
            continue
        if _under_workplace_specific(entry, repo_root):
            names.append(entry.name)
    return names


def cmd_backup_excludes(repo_root: Path, cursor_home: Path, subdir_name: str) -> None:
    skills_only = subdir_name == "skills"
    subdir = cursor_home / subdir_name
    for name in backup_exclude_names(subdir, repo_root, skills_only):
        print(name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("restore-user", help="Symlink user-level adapter exports")
    link_p = sub.add_parser("link-project", help="Symlink project-level adapter exports")
    link_p.add_argument("project", type=Path, help="Target repository path")
    exc_p = sub.add_parser("backup-excludes", help="Print rsync exclude basenames for backup.sh")
    exc_p.add_argument(
        "subdir",
        choices=("skills", "agents", "rules"),
        help="Cursor subdirectory under ~/.cursor",
    )

    args = parser.parse_args()
    repo_root = repo_root_from_script()
    workplace_dir = repo_root / "workplace-specific"
    cursor_home = Path(os.environ.get("CURSOR_HOME", Path.home() / ".cursor"))

    try:
        if args.command == "restore-user":
            restore_user(cursor_home, workplace_dir)
        elif args.command == "link-project":
            link_project(repo_root, args.project, workplace_dir)
        elif args.command == "backup-excludes":
            cmd_backup_excludes(repo_root, cursor_home, args.subdir)
    except AdapterError as exc:
        print(f"workplace-adapters: error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
