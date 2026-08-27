#!/usr/bin/env python3
"""Gate adding libraries to a repo.

Policy (all must pass):
  1. Permissive commercial license (MIT/Apache/BSD/ISC-style) OR Trimble-made
  2. No HIGH/CRITICAL vulnerabilities on the version being added
  3. Human approval (never auto-allow a new/changed dependency)

beforeShellExecution: check + ask
afterShellExecution: remember approved installs so later manifest pins can proceed
preToolUse (Write/StrReplace): block manifest adds unless recently approved
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

USER_AGENT = "CursorLibraryGateHook/1.0 (+https://cursor.com)"
HTTP_TIMEOUT = 8
STATE_PATH = Path.home() / ".cursor/hooks/state/approved-libraries.json"
APPROVAL_TTL_SEC = 4 * 60 * 60
SERIOUS_LABELS = {"HIGH", "CRITICAL"}
SERIOUS_CVSS = 7.0

PERMISSIVE_LICENSES = {
    "0BSD",
    "AFL-3.0",
    "Apache-2.0",
    "Artistic-2.0",
    "BlueOak-1.0.0",
    "BSD",
    "BSD-1-Clause",
    "BSD-2-Clause",
    "BSD-2-Clause-Patent",
    "BSD-3-Clause",
    "BSD-3-Clause-Clear",
    "BSL-1.0",
    "CC0-1.0",
    "ISC",
    "MIT",
    "MIT-0",
    "MIT-CMU",
    "MITNFA",
    "MPL-2.0",  # file-level; does not restrict commercial licensing of the product
    "MS-PL",
    "MulanPSL-2.0",
    "NCSA",
    "OpenSSL",
    "PostgreSQL",
    "PSF-2.0",
    "Python-2.0",
    "Ruby",
    "Unlicense",
    "UPL-1.0",
    "WTFPL",
    "Zlib",
}

LICENSE_ALIASES = {
    "apache": "Apache-2.0",
    "apache2": "Apache-2.0",
    "apache-2": "Apache-2.0",
    "apache 2": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "apache license": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache-2.0": "Apache-2.0",
    "asl 2.0": "Apache-2.0",
    "boost": "BSL-1.0",
    "bsd": "BSD-3-Clause",
    "bsd license": "BSD-3-Clause",
    "bsd-2-clause": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "isc": "ISC",
    "isc license": "ISC",
    "mit": "MIT",
    "mit licence": "MIT",
    "mit license": "MIT",
    "the mit license": "MIT",
    "psf": "PSF-2.0",
    "python": "Python-2.0",
    "unlicense": "Unlicense",
    "zlib": "Zlib",
}

NPM_VALUE_FLAGS = {
    "-C",
    "--cache",
    "--cwd",
    "--filter",
    "--globalconfig",
    "--include",
    "--install-strategy",
    "--loglevel",
    "--omit",
    "--package-lock-only",
    "--prefix",
    "--registry",
    "--save-prefix",
    "--script-shell",
    "--tag",
    "--userconfig",
    "--workspace",
    "-w",
}

PIP_VALUE_FLAGS = {
    "-c",
    "--constraint",
    "-e",
    "--editable",
    "-f",
    "--find-links",
    "-i",
    "--index-url",
    "--extra-index-url",
    "-r",
    "--requirement",
    "--src",
    "--root",
    "--prefix",
    "--user",
    "-t",
    "--target",
    "--platform",
    "--python-version",
    "--implementation",
    "--abi",
    "--log",
    "--config-settings",
    "-C",
}

MANIFEST_NAMES = {
    "package.json",
    "pyproject.toml",
    "pipfile",
    "cargo.toml",
    "go.mod",
    "gemfile",
    "composer.json",
    "pom.xml",
}

LOCKFILE_NAMES = {
    "package-lock.json",
    "npm-shrinkwrap.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lock",
    "bun.lockb",
    "poetry.lock",
    "uv.lock",
    "cargo.lock",
    "go.sum",
    "composer.lock",
    "gemfile.lock",
    "pipfile.lock",
}


@dataclass(frozen=True)
class Pkg:
    ecosystem: str
    name: str
    version: str | None = None
    raw: str = ""
    local: bool = False


def log(msg: str) -> None:
    print(f"gate-library-add: {msg}", file=sys.stderr)


def emit(payload: dict[str, Any]) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.exit(0)


def allow() -> None:
    emit({"permission": "allow"})


def deny(user_message: str, agent_message: str | None = None) -> None:
    payload = {
        "permission": "deny",
        "user_message": user_message,
        "agent_message": agent_message or user_message,
    }
    log(f"deny: {user_message}")
    emit(payload)


def ask(user_message: str, agent_message: str | None = None) -> None:
    payload = {
        "permission": "ask",
        "user_message": user_message,
        "agent_message": agent_message or user_message,
    }
    log(f"ask: {user_message}")
    emit(payload)


def read_stdin() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        deny("Library gate hook received empty input.", "Library gate: empty hook input.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        deny("Library gate hook received invalid JSON.", "Library gate: invalid hook input JSON.")
    if not isinstance(data, dict):
        deny("Library gate hook received a non-object payload.")
    return data


def infer_event(data: dict[str, Any]) -> str:
    name = data.get("hook_event_name")
    if isinstance(name, str) and name:
        return name
    if "composer_mode" in data or (
        "session_id" in data and "command" not in data and "tool_name" not in data
    ):
        return "sessionStart"
    if "output" in data and "command" in data:
        return "afterShellExecution"
    if "tool_name" in data:
        return "preToolUse"
    if "command" in data:
        return "beforeShellExecution"
    return ""


def http_json(url: str, method: str = "GET", body: dict[str, Any] | None = None) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        payload = resp.read()
    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def cvss31_score(vector: str) -> float | None:
    text = vector.strip()
    try:
        return float(text)
    except ValueError:
        pass
    match = re.search(r"CVSS:3\.[01]/(.+)", text)
    if not match:
        return None
    metrics = dict(part.split(":", 1) for part in match.group(1).split("/") if ":" in part)
    av = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}.get(metrics.get("AV", ""))
    ac = {"L": 0.77, "H": 0.44}.get(metrics.get("AC", ""))
    ui = {"N": 0.85, "R": 0.62}.get(metrics.get("UI", ""))
    cia = {"N": 0.0, "L": 0.22, "H": 0.56}
    c, i, a = cia.get(metrics.get("C", "")), cia.get(metrics.get("I", "")), cia.get(metrics.get("A", ""))
    scope = metrics.get("S")
    pr_key = metrics.get("PR")
    if None in (av, ac, ui, c, i, a) or scope not in {"U", "C"} or pr_key not in {"N", "L", "H"}:
        return None
    pr = ({"N": 0.85, "L": 0.62, "H": 0.27} if scope == "U" else {"N": 0.85, "L": 0.68, "H": 0.50})[
        pr_key
    ]
    iss = 1 - (1 - c) * (1 - i) * (1 - a)
    if iss <= 0:
        return 0.0
    if scope == "U":
        impact = 6.42 * iss
        exploit = 8.22 * av * ac * pr * ui
        base = min(10.0, impact + exploit)
    else:
        impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
        exploit = 8.22 * av * ac * pr * ui
        base = min(10.0, 1.08 * (impact + exploit))
    return int(base * 10 + 0.5) / 10.0


def normalize_license_token(token: str) -> str:
    cleaned = token.strip().strip("()[]").strip()
    cleaned = re.sub(r"^licen[cs]e\s*:\s*", "", cleaned, flags=re.I)
    key = re.sub(r"\s+", " ", cleaned).strip().lower()
    key = key.removeprefix("the ").strip()
    if key in LICENSE_ALIASES:
        return LICENSE_ALIASES[key]
    spdx = cleaned.split(" ")[0] if re.match(r"^[A-Za-z0-9.+-]+$", cleaned) else cleaned
    return spdx


def permissive_license(expr: str | None) -> bool:
    if not expr or not str(expr).strip():
        return False
    text = str(expr).strip()
    lowered = text.lower()
    if any(
        bad in lowered
        for bad in (
            "commons clause",
            "sspl",
            "busl",
            "business source",
            "elastic license",
            "noncommercial",
            "non-commercial",
            "cc-by-nc",
            "proprietary",
            "unlicensed",
        )
    ):
        return False

    def eval_expr(s: str) -> bool:
        s = s.strip()
        if s.startswith("(") and _matching_paren(s) == len(s) - 1:
            return eval_expr(s[1:-1])
        or_parts = _split_top(s, " OR ")
        if len(or_parts) > 1:
            return any(eval_expr(p) for p in or_parts)
        and_parts = _split_top(s, " AND ")
        if len(and_parts) > 1:
            return all(eval_expr(p) for p in and_parts)
        with_parts = _split_top(s, " WITH ")
        token = normalize_license_token(with_parts[0])
        if re.search(r"^(AGPL|GPL|LGPL|CC-BY-NC|SSPL|BUSL)", token, re.I):
            return False
        return token in PERMISSIVE_LICENSES or normalize_license_token(token) in PERMISSIVE_LICENSES

    try:
        return eval_expr(text.replace(" || ", " OR ").replace(" or ", " OR ").replace(" and ", " AND "))
    except Exception:
        return False


def _matching_paren(s: str) -> int:
    depth = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _split_top(s: str, sep: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    i = 0
    upper = s.upper()
    needle = sep.upper()
    while i < len(s):
        ch = s[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and upper.startswith(needle, i):
            parts.append(s[start:i])
            i += len(sep)
            start = i
            continue
        i += 1
    parts.append(s[start:])
    return [p.strip() for p in parts if p.strip()] if len(parts) > 1 else [s]


def is_trimble_name(name: str) -> bool:
    lower = name.lower()
    if lower.startswith("@") and "trimble" in lower.split("/", 1)[0]:
        return True
    return bool(re.match(r"^trimble([._-]|$)", lower))


def is_trimble_meta(name: str, blobs: list[str]) -> bool:
    if is_trimble_name(name):
        return True
    joined = "\n".join(b for b in blobs if b).lower()
    if re.search(r"github\.com/trimble(-oss|-inc)?(/|$)", joined):
        return True
    if re.search(r"(^|://)([a-z0-9.-]+\.)?trimble\.com(/|$)", joined):
        return True
    if re.search(r"\btrimble\b", joined):
        # Only count author/publisher-style fields, not arbitrary readme text.
        return True
    return False


def split_shell_segments(command: str) -> list[str]:
    parts = re.split(r"\s*(?:&&|\|\||;|\n)\s*", command)
    return [p.strip() for p in parts if p.strip()]


def strip_value_flags(tokens: list[str], value_flags: set[str]) -> list[str]:
    out: list[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok in value_flags:
            skip_next = True
            continue
        flag, eq, _value = tok.partition("=")
        if eq and flag in value_flags:
            continue
        if tok.startswith("-"):
            continue
        out.append(tok)
    return out


def parse_npm_spec(spec: str) -> Pkg | None:
    raw = spec.strip().strip("'\"")
    if not raw or raw in {".", ".."}:
        return None
    if raw.startswith(("file:", "workspace:", "link:", "./", "../")) or raw.startswith("/"):
        return Pkg("npm", raw, local=True, raw=raw)
    if raw.startswith(("git+", "git://", "github:", "gitlab:", "bitbucket:", "http://", "https://", "ssh://")):
        trimble = bool(re.search(r"github\.com/trimble|github:trimble", raw, re.I))
        name = raw
        return Pkg("npm", name, local=trimble, raw=raw)
    name = raw
    version = None
    if raw.startswith("@"):
        # @scope/name or @scope/name@version
        m = re.match(r"^(@[^/]+/[^@]+)(?:@(.+))?$", raw)
        if not m:
            return Pkg("npm", raw, raw=raw)
        name, version = m.group(1), m.group(2)
    elif "@" in raw:
        name, version = raw.rsplit("@", 1)
        if not name:
            return None
    if version in {"latest", "*"}:
        version = None
    return Pkg("npm", name, version, raw=raw)


def parse_pypi_spec(spec: str) -> Pkg | None:
    raw = spec.strip().strip("'\"")
    if not raw or raw in {".", ".."} or raw.startswith(("-", ".", "/", "git+", "http://", "https://", "svn+")):
        if raw.startswith((".", "/", "file:")):
            return Pkg("PyPI", raw, local=True, raw=raw)
        return None
    name = re.split(r"[=<>!~\[]", raw, maxsplit=1)[0].strip()
    if not name:
        return None
    ver = None
    m = re.search(r"==\s*([0-9A-Za-z._+-]+)", raw)
    if m:
        ver = m.group(1)
    return Pkg("PyPI", name, ver, raw=raw)


def looks_like_package_manager(command: str) -> bool:
    return bool(
        re.search(
            r"(?:^|[\s;&|])(npm|npx|yarn|pnpm|bun|pip(?:3)?|poetry|uv|cargo|composer|bundle|dotnet|gem|go)\b",
            command,
            re.I,
        )
    )


def parse_packages_from_command(command: str) -> list[Pkg]:
    found: list[Pkg] = []
    for segment in split_shell_segments(command):
        found.extend(_parse_one_command(segment))
    # de-dupe
    seen: set[tuple[str, str, str | None]] = set()
    out: list[Pkg] = []
    for pkg in found:
        key = (pkg.ecosystem, pkg.name, pkg.version)
        if key in seen:
            continue
        seen.add(key)
        out.append(pkg)
    return out


def _parse_one_command(segment: str) -> list[Pkg]:
    try:
        tokens = shlex.split(segment)
    except ValueError:
        tokens = segment.split()
    if not tokens:
        return []
    # drop env assignments
    while tokens and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]):
        tokens.pop(0)
    if not tokens:
        return []
    lower = [t.lower() for t in tokens]

    def idx(name: str) -> int:
        return lower.index(name) if name in lower else -1

    # python -m pip / python3 -m pip
    if "pip" in lower or "pip3" in lower:
        pip_at = idx("pip") if idx("pip") >= 0 else idx("pip3")
        rest = tokens[pip_at + 1 :]
        rest_l = [t.lower() for t in rest]
        if rest and rest_l[0] == "install":
            args = strip_value_flags(rest[1:], PIP_VALUE_FLAGS)
            pkgs = []
            for spec in args:
                if spec.startswith("-") or spec in {"-r", "--requirement"}:
                    continue
                parsed = parse_pypi_spec(spec)
                if parsed and not parsed.local:
                    pkgs.append(parsed)
            return pkgs
        return []

    if "uv" in lower:
        uv_at = idx("uv")
        rest = tokens[uv_at + 1 :]
        rest_l = [t.lower() for t in rest]
        if rest_l[:1] == ["add"] or rest_l[:2] == ["pip", "install"]:
            start = 1 if rest_l[:1] == ["add"] else 2
            args = strip_value_flags(rest[start:], PIP_VALUE_FLAGS | {"--index", "--default-index"})
            return [p for spec in args if (p := parse_pypi_spec(spec)) and not p.local]
        return []

    if "poetry" in lower:
        at = idx("poetry")
        rest = tokens[at + 1 :]
        if rest and rest[0].lower() == "add":
            args = strip_value_flags(rest[1:], {"--directory", "-C", "--source", "--extras", "-E", "--python"})
            return [p for spec in args if (p := parse_pypi_spec(spec)) and not p.local]
        return []

    if "npm" in lower:
        at = idx("npm")
        rest = tokens[at + 1 :]
        rest_l = [t.lower() for t in rest]
        if not rest:
            return []
        verb = rest_l[0]
        if verb in {"install", "i", "add", "in", "inst", "insta", "instal"}:
            if any(t in {"-g", "--global"} for t in rest):
                return []
            args = strip_value_flags(rest[1:], NPM_VALUE_FLAGS)
            return [p for spec in args if (p := parse_npm_spec(spec))]
        return []

    if "yarn" in lower:
        at = idx("yarn")
        rest = tokens[at + 1 :]
        rest_l = [t.lower() for t in rest]
        if rest and rest_l[0] == "add":
            args = strip_value_flags(rest[1:], NPM_VALUE_FLAGS | {"--cwd"})
            return [p for spec in args if (p := parse_npm_spec(spec))]
        return []

    if "pnpm" in lower:
        at = idx("pnpm")
        rest = tokens[at + 1 :]
        rest_l = [t.lower() for t in rest]
        if rest and rest_l[0] in {"add", "install", "i"}:
            args = strip_value_flags(rest[1:], NPM_VALUE_FLAGS | {"--filter"})
            return [p for spec in args if (p := parse_npm_spec(spec))]
        return []

    if "bun" in lower:
        at = idx("bun")
        rest = tokens[at + 1 :]
        rest_l = [t.lower() for t in rest]
        if rest and rest_l[0] in {"add", "install", "i"}:
            args = strip_value_flags(rest[1:], NPM_VALUE_FLAGS)
            return [p for spec in args if (p := parse_npm_spec(spec))]
        return []

    if "cargo" in lower:
        at = idx("cargo")
        rest = tokens[at + 1 :]
        if rest and rest[0].lower() == "add":
            args = strip_value_flags(
                rest[1:],
                {"--features", "-F", "--rename", "--path", "--git", "--branch", "--tag", "--rev", "--registry"},
            )
            pkgs = []
            for spec in args:
                name, _, ver = spec.partition("@")
                if name:
                    pkgs.append(Pkg("crates.io", name, ver or None, raw=spec))
            return pkgs
        return []

    if "composer" in lower:
        at = idx("composer")
        rest = tokens[at + 1 :]
        if rest and rest[0].lower() == "require":
            args = strip_value_flags(rest[1:], {"--working-dir", "-d"})
            pkgs = []
            for spec in args:
                raw = spec.strip()
                name, _, ver = raw.partition(":")
                if "/" in name:
                    pkgs.append(Pkg("Packagist", name, ver or None, raw=raw))
            return pkgs
        return []

    if "bundle" in lower:
        at = idx("bundle")
        rest = tokens[at + 1 :]
        if rest and rest[0].lower() == "add":
            args = [t for t in rest[1:] if not t.startswith("-")]
            if args:
                ver = None
                if "-v" in rest:
                    try:
                        ver = rest[rest.index("-v") + 1]
                    except Exception:
                        ver = None
                return [Pkg("RubyGems", args[0], ver, raw=args[0])]
        return []

    if "gem" in lower:
        at = idx("gem")
        rest = tokens[at + 1 :]
        if rest and rest[0].lower() == "install":
            args = [t for t in rest[1:] if not t.startswith("-")]
            ver = None
            for flag in ("-v", "--version"):
                if flag in rest:
                    try:
                        ver = rest[rest.index(flag) + 1]
                    except Exception:
                        ver = None
            return [Pkg("RubyGems", spec, ver, raw=spec) for spec in args]
        return []

    if "dotnet" in lower:
        at = idx("dotnet")
        rest = tokens[at + 1 :]
        rest_l = [t.lower() for t in rest]
        if rest_l[:2] == ["add", "package"] and len(rest) >= 3:
            name = rest[2]
            ver = None
            for i, tok in enumerate(rest):
                if tok in {"-v", "--version"} and i + 1 < len(rest):
                    ver = rest[i + 1]
            return [Pkg("NuGet", name, ver, raw=name)]
        return []

    if "go" in lower:
        at = idx("go")
        rest = tokens[at + 1 :]
        if rest and rest[0].lower() in {"get", "install"}:
            pkgs = []
            for spec in rest[1:]:
                if spec.startswith("-"):
                    continue
                name, _, ver = spec.partition("@")
                if name:
                    pkgs.append(Pkg("Go", name, ver or None, raw=spec))
            return pkgs
        return []

    return []


def is_lockfile(path: str) -> bool:
    return Path(path).name.lower() in LOCKFILE_NAMES


def is_manifest(path: str) -> bool:
    name = Path(path).name.lower()
    if name in MANIFEST_NAMES:
        return True
    if name.endswith(".csproj") or name.endswith(".fsproj") or name.endswith(".vbproj"):
        return True
    if re.match(r"requirements.*\.txt$", name):
        return True
    return False


def read_text(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception:
        return None


def npm_deps_from_json(text: str) -> dict[str, str]:
    data = json.loads(text)
    out: dict[str, str] = {}
    if not isinstance(data, dict):
        return out
    for key in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        block = data.get(key) or {}
        if isinstance(block, dict):
            for name, ver in block.items():
                out[str(name)] = str(ver)
    return out


def pypi_reqs_from_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-")):
            continue
        pkg = parse_pypi_spec(stripped)
        if pkg and not pkg.local:
            out[pkg.name.lower()] = pkg.version or stripped
    return out


def pypi_deps_from_pyproject(text: str) -> dict[str, str]:
    data = tomllib.loads(text)
    out: dict[str, str] = {}

    def add_spec(spec: str) -> None:
        pkg = parse_pypi_spec(spec)
        if pkg and not pkg.local:
            out[pkg.name.lower()] = pkg.version or spec

    project = data.get("project") or {}
    for spec in project.get("dependencies") or []:
        if isinstance(spec, str):
            add_spec(spec)
    opt = project.get("optional-dependencies") or {}
    if isinstance(opt, dict):
        for specs in opt.values():
            for spec in specs or []:
                if isinstance(spec, str):
                    add_spec(spec)
    poetry = ((data.get("tool") or {}).get("poetry") or {})
    for section in ("dependencies", "dev-dependencies"):
        block = poetry.get(section) or {}
        if isinstance(block, dict):
            for name, ver in block.items():
                if name.lower() == "python":
                    continue
                out[str(name).lower()] = str(ver) if not isinstance(ver, dict) else str(ver.get("version") or ver)
    groups = poetry.get("group") or {}
    if isinstance(groups, dict):
        for group in groups.values():
            if isinstance(group, dict):
                deps = group.get("dependencies") or {}
                if isinstance(deps, dict):
                    for name, ver in deps.items():
                        out[str(name).lower()] = str(ver)
    return out


def cargo_deps_from_toml(text: str) -> dict[str, str]:
    data = tomllib.loads(text)
    out: dict[str, str] = {}
    sections = [
        data.get("dependencies") or {},
        data.get("dev-dependencies") or {},
        data.get("build-dependencies") or {},
        (data.get("workspace") or {}).get("dependencies") or {},
    ]
    for block in sections:
        if not isinstance(block, dict):
            continue
        for name, ver in block.items():
            if isinstance(ver, dict):
                if ver.get("path") or ver.get("workspace") is True:
                    continue
                out[str(name)] = str(ver.get("version") or "")
            else:
                out[str(name)] = str(ver)
    return out


def go_mods(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("require ("):
            in_block = True
            continue
        if in_block and stripped == ")":
            in_block = False
            continue
        m = re.match(r"require\s+(\S+)\s+(\S+)", stripped)
        if m:
            out[m.group(1)] = m.group(2)
            continue
        if in_block:
            m = re.match(r"(\S+)\s+(\S+)", stripped)
            if m and not m.group(1).startswith("//"):
                out[m.group(1)] = m.group(2)
    return out


def composer_deps(text: str) -> dict[str, str]:
    data = json.loads(text)
    out: dict[str, str] = {}
    for key in ("require", "require-dev"):
        block = data.get(key) or {}
        if isinstance(block, dict):
            for name, ver in block.items():
                if name.lower() in {"php", "composer-plugin-api"} or name.lower().startswith("ext-"):
                    continue
                out[str(name)] = str(ver)
    return out


def gemfile_deps(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in re.finditer(r"""gem\s+['"]([^'"]+)['"](?:\s*,\s*['"]([^'"]+)['"])?""", text):
        out[m.group(1)] = m.group(2) or ""
    return out


def csproj_deps(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        for m in re.finditer(
            r"""<PackageReference[^>]*Include=["']([^"']+)["'][^>]*(?:Version=["']([^"']+)["'])?""",
            text,
            re.I,
        ):
            out[m.group(1)] = m.group(2) or ""
        return out
    for el in root.iter():
        tag = el.tag.split("}", 1)[-1]
        if tag != "PackageReference":
            continue
        name = el.attrib.get("Include") or el.attrib.get("Update")
        ver = el.attrib.get("Version") or ""
        if name:
            out[name] = ver
    return out


def pipfile_deps(text: str) -> dict[str, str]:
    data = tomllib.loads(text)
    out: dict[str, str] = {}
    for key in ("packages", "dev-packages"):
        block = data.get(key) or {}
        if isinstance(block, dict):
            for name, ver in block.items():
                out[str(name).lower()] = str(ver) if not isinstance(ver, dict) else str(ver.get("version") or "")
    return out


def manifest_ecosystem(path: str) -> str | None:
    name = Path(path).name.lower()
    if name == "package.json":
        return "npm"
    if name in {"pyproject.toml", "pipfile"} or re.match(r"requirements.*\.txt$", name):
        return "PyPI"
    if name == "cargo.toml":
        return "crates.io"
    if name == "go.mod":
        return "Go"
    if name == "gemfile":
        return "RubyGems"
    if name == "composer.json":
        return "Packagist"
    if name.endswith((".csproj", ".fsproj", ".vbproj")):
        return "NuGet"
    return None


def deps_from_manifest(path: str, text: str) -> dict[str, str]:
    name = Path(path).name.lower()
    if name == "package.json":
        return npm_deps_from_json(text)
    if re.match(r"requirements.*\.txt$", name):
        return pypi_reqs_from_text(text)
    if name == "pyproject.toml":
        return pypi_deps_from_pyproject(text)
    if name == "pipfile":
        return pipfile_deps(text)
    if name == "cargo.toml":
        return cargo_deps_from_toml(text)
    if name == "go.mod":
        return go_mods(text)
    if name == "composer.json":
        return composer_deps(text)
    if name == "gemfile":
        return gemfile_deps(text)
    if name.endswith((".csproj", ".fsproj", ".vbproj")):
        return csproj_deps(text)
    return {}


def apply_str_replace(original: str, old: str, new: str) -> str:
    if old and old in original:
        return original.replace(old, new, 1)
    return new if not original else original + "\n" + new


def pkgs_from_dep_diff(path: str, before: str, after: str) -> list[Pkg]:
    eco = manifest_ecosystem(path)
    if not eco:
        return []
    try:
        old = deps_from_manifest(path, before) if before.strip() else {}
        new = deps_from_manifest(path, after) if after.strip() else {}
    except Exception as exc:
        deny(
            f"Could not parse {Path(path).name} to check new libraries ({exc}).",
            f"Library gate: failed to parse {path}: {exc}. Do not add dependencies by editing this file.",
        )
    pkgs: list[Pkg] = []
    for name, ver in new.items():
        prev = old.get(name)
        if prev == ver:
            continue
        # existing name with same version skipped; new name or version change is gated
        if prev is not None and _same_requested_version(prev, ver):
            continue
        version = _concrete_version(ver)
        pkgs.append(Pkg(eco, name, version, raw=f"{name}@{ver}"))
    return pkgs


def _same_requested_version(a: str, b: str) -> bool:
    return _concrete_version(a) == _concrete_version(b) and a.strip() == b.strip()


def _concrete_version(spec: str) -> str | None:
    text = str(spec).strip().strip("'\"")
    text = re.sub(r"^(workspace:|file:|link:).*", "", text)
    if not text:
        return None
    m = re.search(r"(\d+\.\d+\.\d+(?:[A-Za-z0-9._+-]*))", text)
    if m:
        return m.group(1)
    m = re.search(r"v?(\d+\.\d+\.\d+)", text)
    return m.group(1) if m else None


def load_approvals() -> list[dict[str, Any]]:
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        items = data.get("packages") if isinstance(data, dict) else data
        if not isinstance(items, list):
            return []
        now = time.time()
        return [p for p in items if now - float(p.get("ts", 0)) < APPROVAL_TTL_SEC]
    except Exception:
        return []


def save_approvals(items: list[dict[str, Any]]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"packages": items}, indent=2), encoding="utf-8")


def record_approvals(pkgs: list[Pkg]) -> None:
    items = load_approvals()
    now = time.time()
    for pkg in pkgs:
        items.append(
            {
                "ecosystem": pkg.ecosystem,
                "name": pkg.name,
                "version": pkg.version,
                "ts": now,
            }
        )
    save_approvals(items[-200:])


def recently_approved(pkg: Pkg) -> bool:
    for item in load_approvals():
        if item.get("ecosystem") != pkg.ecosystem:
            continue
        if str(item.get("name", "")).lower() != pkg.name.lower():
            continue
        approved_ver = item.get("version")
        if not pkg.version or not approved_ver:
            return True
        if str(approved_ver) == str(pkg.version):
            return True
    return False


def deps_dev_system(ecosystem: str) -> str | None:
    return {
        "npm": "NPM",
        "PyPI": "PYPI",
        "crates.io": "CARGO",
        "Go": "GO",
        "NuGet": "NUGET",
        "RubyGems": "RUBYGEMS",
    }.get(ecosystem)


def osv_ecosystem(ecosystem: str) -> str:
    return {
        "npm": "npm",
        "PyPI": "PyPI",
        "crates.io": "crates.io",
        "Go": "Go",
        "NuGet": "NuGet",
        "RubyGems": "RubyGems",
        "Packagist": "Packagist",
    }.get(ecosystem, ecosystem)


def lookup_latest_version(pkg: Pkg) -> str | None:
    try:
        if pkg.ecosystem == "npm":
            encoded = urllib.parse.quote(pkg.name, safe="@")
            data = http_json(f"https://registry.npmjs.org/{encoded}/latest")
            return (data or {}).get("version")
        if pkg.ecosystem == "PyPI":
            data = http_json(f"https://pypi.org/pypi/{urllib.parse.quote(pkg.name)}/json")
            return ((data or {}).get("info") or {}).get("version")
        if pkg.ecosystem == "crates.io":
            data = http_json(f"https://crates.io/api/v1/crates/{urllib.parse.quote(pkg.name)}")
            return ((data or {}).get("crate") or {}).get("max_stable_version") or (
                (data or {}).get("crate") or {}
            ).get("max_version")
        if pkg.ecosystem == "Go":
            encoded = urllib.parse.quote(pkg.name, safe="")
            data = http_json(f"https://proxy.golang.org/{encoded}/@latest")
            return (data or {}).get("Version")
        if pkg.ecosystem == "RubyGems":
            data = http_json(f"https://rubygems.org/api/v1/versions/{urllib.parse.quote(pkg.name)}/latest.json")
            return (data or {}).get("version")
        if pkg.ecosystem == "NuGet":
            data = http_json(
                "https://api.nuget.org/v3-flatcontainer/"
                f"{urllib.parse.quote(pkg.name.lower())}/index.json"
            )
            versions = (data or {}).get("versions") or []
            return versions[-1] if versions else None
        if pkg.ecosystem == "Packagist":
            data = http_json(f"https://repo.packagist.org/p2/{pkg.name}.json")
            packages = ((data or {}).get("packages") or {}).get(pkg.name) or []
            if packages:
                return packages[0].get("version_normalized") or packages[0].get("version")
        system = deps_dev_system(pkg.ecosystem)
        if system:
            encoded = urllib.parse.quote(pkg.name, safe="")
            data = http_json(f"https://api.deps.dev/v3/systems/{system}/packages/{encoded}")
            versions = (data or {}).get("versions") or []
            for item in versions:
                if item.get("isDefault"):
                    return (item.get("versionKey") or {}).get("version")
            if versions:
                return (versions[0].get("versionKey") or {}).get("version")
    except Exception as exc:
        log(f"latest version lookup failed for {pkg.name}: {exc}")
    return None


def fetch_license_and_trimble(pkg: Pkg, version: str) -> tuple[str | None, bool, list[str]]:
    notes: list[str] = []
    license_expr: str | None = None
    trimble = is_trimble_name(pkg.name)
    meta_blobs: list[str] = []

    system = deps_dev_system(pkg.ecosystem)
    if system:
        try:
            encoded_name = urllib.parse.quote(pkg.name, safe="")
            encoded_ver = urllib.parse.quote(version, safe="")
            data = http_json(
                f"https://api.deps.dev/v3/systems/{system}/packages/{encoded_name}/versions/{encoded_ver}"
            )
            licenses = (data or {}).get("licenses") or []
            if licenses:
                license_expr = " AND ".join(str(x) for x in licenses)
            for link in (data or {}).get("links") or []:
                meta_blobs.append(str(link.get("url") or ""))
        except urllib.error.HTTPError as exc:
            notes.append(f"deps.dev HTTP {exc.code}")
        except Exception as exc:
            notes.append(f"deps.dev: {exc}")

    try:
        if pkg.ecosystem == "npm":
            encoded = urllib.parse.quote(pkg.name, safe="@")
            data = http_json(f"https://registry.npmjs.org/{encoded}/{urllib.parse.quote(version)}")
            license_expr = license_expr or (data or {}).get("license")
            if isinstance(license_expr, dict):
                license_expr = license_expr.get("type")
            if isinstance(license_expr, list):
                license_expr = " OR ".join(str(x) for x in license_expr)
            meta_blobs.extend(
                [
                    str((data or {}).get("homepage") or ""),
                    str(((data or {}).get("repository") or {}).get("url") or (data or {}).get("repository") or ""),
                    str(((data or {}).get("publisher") or {}).get("name") or ""),
                    str(((data or {}).get("_npmUser") or {}).get("name") or ""),
                ]
            )
            for person in (data or {}).get("maintainers") or []:
                if isinstance(person, dict):
                    meta_blobs.append(str(person.get("name") or ""))
                    meta_blobs.append(str(person.get("email") or ""))
            author = (data or {}).get("author")
            if isinstance(author, dict):
                meta_blobs.append(str(author.get("name") or ""))
            elif isinstance(author, str):
                meta_blobs.append(author)
        elif pkg.ecosystem == "PyPI":
            data = http_json(f"https://pypi.org/pypi/{urllib.parse.quote(pkg.name)}/{urllib.parse.quote(version)}/json")
            info = (data or {}).get("info") or {}
            license_expr = license_expr or info.get("license_expression") or info.get("license")
            meta_blobs.extend(
                [
                    str(info.get("author") or ""),
                    str(info.get("author_email") or ""),
                    str(info.get("home_page") or ""),
                    str(info.get("package_url") or ""),
                ]
            )
            urls = info.get("project_urls") or {}
            if isinstance(urls, dict):
                meta_blobs.extend(str(v) for v in urls.values())
        elif pkg.ecosystem == "crates.io":
            data = http_json(
                f"https://crates.io/api/v1/crates/{urllib.parse.quote(pkg.name)}/{urllib.parse.quote(version)}"
            )
            license_expr = license_expr or ((data or {}).get("version") or {}).get("license")
            crate = (data or {}).get("crate") or {}
            meta_blobs.extend([str(crate.get("homepage") or ""), str(crate.get("repository") or "")])
        elif pkg.ecosystem == "Packagist":
            data = http_json(f"https://repo.packagist.org/p2/{pkg.name}.json")
            versions = ((data or {}).get("packages") or {}).get(pkg.name) or []
            match = next((v for v in versions if str(v.get("version") or "").lstrip("v") == version.lstrip("v")), None)
            match = match or (versions[0] if versions else None)
            if match:
                licenses = match.get("license") or []
                license_expr = license_expr or " OR ".join(licenses) if licenses else license_expr
                meta_blobs.extend(
                    [
                        str(match.get("homepage") or ""),
                        str((match.get("source") or {}).get("url") or ""),
                        str(match.get("authors") or ""),
                    ]
                )
        elif pkg.ecosystem == "RubyGems":
            data = http_json(f"https://rubygems.org/api/v2/rubygems/{urllib.parse.quote(pkg.name)}/versions/{urllib.parse.quote(version)}.json")
            licenses = (data or {}).get("licenses") or []
            license_expr = license_expr or " OR ".join(licenses) if licenses else license_expr
            meta_blobs.extend([str((data or {}).get("homepage_uri") or ""), str((data or {}).get("source_code_uri") or "")])
        elif pkg.ecosystem == "Go":
            encoded = urllib.parse.quote(pkg.name, safe="")
            meta_blobs.append(pkg.name)
            if "trimble" in pkg.name.lower():
                trimble = True
    except urllib.error.HTTPError as exc:
        notes.append(f"registry HTTP {exc.code}")
    except Exception as exc:
        notes.append(f"registry: {exc}")

    if pkg.ecosystem == "NuGet" and not license_expr:
        try:
            lower = pkg.name.lower()
            url = (
                f"https://api.nuget.org/v3-flatcontainer/{urllib.parse.quote(lower)}/"
                f"{urllib.parse.quote(version)}/{urllib.parse.quote(lower)}.nuspec"
            )
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                xml_text = resp.read().decode("utf-8", errors="replace")
            root = ElementTree.fromstring(xml_text)
            for el in root.iter():
                tag = el.tag.split("}", 1)[-1]
                if tag == "license" and (el.text or "").strip():
                    license_expr = el.text.strip()
                if tag == "licenseUrl" and (el.text or "").strip():
                    meta_blobs.append(el.text.strip())
                if tag in {"authors", "owners", "projectUrl", "repository"} and (el.text or el.attrib.get("url")):
                    meta_blobs.append(el.text or el.attrib.get("url") or "")
        except Exception as exc:
            notes.append(f"nuget nuspec: {exc}")

    if not trimble:
        trimble = is_trimble_meta(pkg.name, meta_blobs)
    return license_expr, trimble, notes


def serious_vulns(pkg: Pkg, version: str) -> list[str]:
    try:
        data = http_json(
            "https://api.osv.dev/v1/query",
            method="POST",
            body={
                "version": version,
                "package": {"name": pkg.name, "ecosystem": osv_ecosystem(pkg.ecosystem)},
            },
        )
    except Exception as exc:
        raise RuntimeError(f"OSV lookup failed for {pkg.name}@{version}: {exc}") from exc
    vulns = (data or {}).get("vulns") or []
    serious: list[str] = []
    for vuln in vulns:
        label = str((vuln.get("database_specific") or {}).get("severity") or "").upper()
        scores: list[float] = []
        for sev in vuln.get("severity") or []:
            raw = str(sev.get("score") or "")
            parsed = cvss31_score(raw)
            if parsed is not None:
                scores.append(parsed)
        max_score = max(scores) if scores else None
        is_serious = label in SERIOUS_LABELS or (max_score is not None and max_score >= SERIOUS_CVSS)
        if is_serious:
            ident = vuln.get("id") or "unknown"
            summary = (vuln.get("summary") or "").strip()
            extra = f"{label or (f'CVSS {max_score}' if max_score is not None else 'serious')}"
            serious.append(f"{ident} ({extra})" + (f": {summary}" if summary else ""))
    return serious


def evaluate_packages(pkgs: list[Pkg]) -> tuple[list[str], list[str], list[Pkg]]:
    """Return (failures, summaries, resolved_pkgs). Failures block; summaries are for the ask prompt."""
    failures: list[str] = []
    summaries: list[str] = []
    resolved: list[Pkg] = []
    for pkg in pkgs:
        if pkg.local:
            summaries.append(f"{pkg.name} (local/first-party path; skipped registry checks)")
            resolved.append(pkg)
            continue
        trimble_by_name = is_trimble_name(pkg.name)
        version = pkg.version
        if version and not re.match(r"^[0-9A-Za-z]", version):
            version = version.lstrip("^~>=<")
        if not version or not re.search(r"\d", version):
            latest = lookup_latest_version(pkg)
            if not latest:
                if trimble_by_name:
                    summaries.append(
                        f"{pkg.name} (Trimble-made; not on public registries, skipped license/OSV)"
                    )
                    resolved.append(pkg)
                    continue
                failures.append(
                    f"{pkg.name}: could not resolve a concrete version, so license/vulnerability checks cannot run"
                )
                continue
            version = latest
        checked = Pkg(pkg.ecosystem, pkg.name, version, raw=pkg.raw)
        try:
            license_expr, trimble, notes = fetch_license_and_trimble(checked, version)
        except Exception as exc:
            if trimble_by_name:
                license_expr, trimble, notes = None, True, [str(exc)]
            else:
                failures.append(f"{pkg.name}@{version}: license lookup failed ({exc})")
                continue
        trimble = trimble or trimble_by_name
        license_ok = permissive_license(license_expr)
        origin = "Trimble-made" if trimble else (license_expr or "unknown license")
        if not license_ok and not trimble:
            extra = f" ({'; '.join(notes)})" if notes else ""
            failures.append(
                f"{pkg.name}@{version}: license {license_expr or 'unknown'} is not a permissive commercial "
                f"license (MIT/Apache/BSD/ISC-style) and the package is not Trimble-made{extra}"
            )
            continue
        try:
            vulns = serious_vulns(checked, version)
        except Exception as exc:
            if trimble:
                summaries.append(
                    f"{pkg.name}@{version} (Trimble-made; vulnerability lookup unavailable, human must still approve)"
                )
                resolved.append(checked)
                continue
            failures.append(str(exc))
            continue
        if vulns:
            failures.append(
                f"{pkg.name}@{version}: serious vulnerabilities: " + "; ".join(vulns)
            )
            continue
        summaries.append(
            f"{pkg.name}@{version} ({origin}"
            + (f", license {license_expr}" if trimble and license_expr else "")
            + ", no HIGH/CRITICAL vulns on this version)"
        )
        resolved.append(checked)
    return failures, summaries, resolved


def handle_before_shell(data: dict[str, Any]) -> None:
    command = str(data.get("command") or "")
    if not looks_like_package_manager(command):
        allow()
    pkgs = parse_packages_from_command(command)
    if not pkgs:
        allow()
    failures, summaries, resolved = evaluate_packages(pkgs)
    if failures:
        reason = "Blocked adding libraries:\n- " + "\n- ".join(failures)
        deny(
            reason,
            reason
            + "\nUse a permissively licensed, non-vulnerable version (or a Trimble package), then retry. "
            "A human still has to approve the install.",
        )
    names = ", ".join(summaries)
    ask(
        "Approve adding this library to the repo?\n" + "\n".join(f"- {s}" for s in summaries),
        "Library gate: "
        + names
        + ". Waiting for a human to approve the install. Do not work around this with manifest edits.",
    )


def handle_after_shell(data: dict[str, Any]) -> None:
    command = str(data.get("command") or "")
    pkgs = parse_packages_from_command(command)
    if pkgs:
        record_approvals(pkgs)
        log(f"recorded approval for {[p.raw or p.name for p in pkgs]}")
    emit({})


def new_contents_from_tool(path: str, tool_input: dict[str, Any]) -> tuple[str, str]:
    before = read_text(path) or ""
    if "contents" in tool_input and tool_input.get("contents") is not None:
        return before, str(tool_input.get("contents") or "")
    old = str(tool_input.get("old_string") or tool_input.get("oldString") or "")
    new = str(tool_input.get("new_string") or tool_input.get("newString") or "")
    if old or new:
        return before, apply_str_replace(before, old, new)
    return before, before


def handle_pre_tool(data: dict[str, Any]) -> None:
    tool = str(data.get("tool_name") or "")
    if tool not in {"Write", "StrReplace"}:
        allow()
    tool_input = data.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        allow()
    path = str(tool_input.get("path") or tool_input.get("file_path") or "")
    if not path:
        allow()
    if is_lockfile(path):
        allow()
    if not is_manifest(path):
        allow()
    before, after = new_contents_from_tool(path, tool_input)
    if before == after:
        allow()
    pkgs = pkgs_from_dep_diff(path, before, after)
    if not pkgs:
        allow()
    pending = [p for p in pkgs if not recently_approved(p)]
    if not pending:
        allow()
    failures, summaries, _resolved = evaluate_packages(pending)
    if failures:
        reason = "Blocked adding libraries via " + Path(path).name + ":\n- " + "\n- ".join(failures)
        deny(
            reason,
            reason
            + "\nDo not add this dependency. Choose a permissively licensed, non-vulnerable version "
            "(or a Trimble package).",
        )
    listing = "\n".join(f"- {s}" for s in summaries)
    deny(
        "New libraries cannot be added by editing "
        + Path(path).name
        + " directly. Run a package-manager install so a human can approve it.\n"
        + listing,
        "Library gate: "
        + Path(path).name
        + " would add:\n"
        + listing
        + "\nLicense and vulnerability checks passed, but human approval is required. "
        "Use npm install / pip install / cargo add / go get / etc. for these packages. "
        "After the human approves the install, you may pin the same version in the manifest.",
    )


def handle_session_start() -> None:
    emit(
        {
            "additional_context": (
                "Library policy: any library added to this repo must (1) have a permissive commercial "
                "license such as MIT, Apache-2.0, BSD, or ISC, or be Trimble-made; (2) have no HIGH or "
                "CRITICAL vulnerabilities on the version being added; and (3) be approved by a human. "
                "Add dependencies with the package manager (npm/pnpm/yarn/pip/poetry/uv/cargo/go/etc.), "
                "not by editing manifests first."
            )
        }
    )


def run_self_test() -> int:
    failures = 0

    def check(cond: bool, msg: str) -> None:
        nonlocal failures
        if not cond:
            print(f"FAIL {msg}")
            failures += 1
        else:
            print(f"ok   {msg}")

    check(permissive_license("MIT"), "MIT is permissive")
    check(permissive_license("MIT OR Apache-2.0"), "MIT OR Apache-2.0 is permissive")
    check(permissive_license("Apache-2.0"), "Apache-2.0 is permissive")
    check(not permissive_license("GPL-3.0-or-later"), "GPL is not permissive")
    check(not permissive_license("MIT AND GPL-3.0"), "MIT AND GPL is not permissive")
    check(not permissive_license(""), "empty license is not permissive")
    check(is_trimble_name("@trimble/foo"), "Trimble npm scope")
    check(is_trimble_name("@trimble-oss/sdk"), "Trimble-oss scope")
    check(is_trimble_name("trimble-identity"), "Trimble name prefix")
    check(not is_trimble_name("lodash"), "lodash is not Trimble")

    lodash = parse_packages_from_command("npm install lodash@4.18.1")
    check(len(lodash) == 1 and lodash[0].name == "lodash" and lodash[0].version == "4.18.1", "parse npm install")
    check(parse_packages_from_command("npm test") == [], "npm test adds nothing")
    check(parse_packages_from_command("npm ci") == [], "npm ci adds nothing")
    check(parse_packages_from_command("npm install") == [], "bare npm install adds nothing")
    scoped = parse_packages_from_command("yarn add -D @types/node@20.0.0")
    check(len(scoped) == 1 and scoped[0].name == "@types/node", "parse scoped yarn add")
    pip = parse_packages_from_command("pip install requests==2.32.3")
    check(len(pip) == 1 and pip[0].ecosystem == "PyPI" and pip[0].version == "2.32.3", "parse pip install")
    check(parse_packages_from_command("pip install -r requirements.txt") == [], "pip -r is not a new library")
    extra = parse_packages_from_command("pip install -r requirements.txt requests")
    check(len(extra) == 1 and extra[0].name == "requests", "pip -r still detects extra packages")
    check(parse_packages_from_command("npm install -g lodash") == [], "global npm install is not a repo add")
    cargo = parse_packages_from_command("cargo add serde@1.0.210")
    check(len(cargo) == 1 and cargo[0].ecosystem == "crates.io", "parse cargo add")
    go = parse_packages_from_command("go get github.com/gin-gonic/gin@v1.9.1")
    check(len(go) == 1 and go[0].ecosystem == "Go", "parse go get")
    mixed = parse_packages_from_command("cd foo && npm install left-pad")
    check(len(mixed) == 1 and mixed[0].name == "left-pad", "parse compound command")

    score = cvss31_score("CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H")
    check(score is not None and score >= 7.0, f"HIGH CVSS parses as serious ({score})")

    # Live registry checks (skip if offline)
    try:
        fails, summaries, _ = evaluate_packages([Pkg("npm", "ffmpeg-static", "5.3.0")])
        check(any("license" in f.lower() or "GPL" in f for f in fails), f"ffmpeg-static GPL denied: {fails}")
        fails, summaries, _ = evaluate_packages([Pkg("npm", "lodash", "4.17.21")])
        check(any("vulnerabilit" in f.lower() for f in fails), f"lodash@4.17.21 vulns denied: {fails}")
        fails, summaries, _ = evaluate_packages([Pkg("npm", "lodash", "4.18.1")])
        check(not fails and summaries, f"lodash@4.18.1 allowed by automated checks: {fails} {summaries}")
    except Exception as exc:
        print(f"skip live checks: {exc}")

    print("self-test failures:", failures)
    return 1 if failures else 0


def main() -> None:
    if "--self-test" in sys.argv:
        sys.exit(run_self_test())
    try:
        data = read_stdin()
        event = infer_event(data)
        if event == "sessionStart":
            handle_session_start()
        elif event == "beforeShellExecution":
            handle_before_shell(data)
        elif event == "afterShellExecution":
            handle_after_shell(data)
        elif event == "preToolUse":
            handle_pre_tool(data)
        else:
            # Unknown event: do not block unrelated hooks.
            if "command" in data and "tool_name" not in data:
                handle_before_shell(data)
            emit({})
    except SystemExit:
        raise
    except Exception as exc:
        deny(
            f"Library gate failed closed: {exc}",
            f"Library gate encountered an error and blocked the action: {exc}",
        )


if __name__ == "__main__":
    main()
