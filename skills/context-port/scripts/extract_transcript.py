#!/usr/bin/env python3
"""Extract user/assistant prose from a Cursor agent transcript JSONL."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)
TIMESTAMP_RE = re.compile(r"<timestamp>.*?</timestamp>\s*", re.DOTALL)
UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)
CITATION_RE = re.compile(r"\[[^\]]+\]\(([0-9a-f-]{36})\)", re.I)

KEEP_LAST_ROUNDS = 14
MAX_OUTPUT_CHARS = 80_000


def clean_user_text(text: str) -> str:
    text = TIMESTAMP_RE.sub("", text)
    match = USER_QUERY_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def is_skippable_text(text: str) -> bool:
    stripped = text.strip()
    return not stripped or stripped == "[REDACTED]"


def clean_assistant_text(text: str) -> str:
    lines = [line for line in text.splitlines() if line.strip() != "[REDACTED]"]
    return "\n".join(lines).strip()


def prose_from_content(content: object) -> list[str]:
    if isinstance(content, str):
        return [content] if not is_skippable_text(content) else []
    if not isinstance(content, list):
        return []
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = block.get("text") or ""
        if is_skippable_text(text):
            continue
        parts.append(text)
    return parts


def parse_jsonl(path: Path) -> list[tuple[str, str]]:
    turns: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        role = record.get("role")
        message = record.get("message")
        if role not in ("user", "assistant") or not isinstance(message, dict):
            continue
        for chunk in prose_from_content(message.get("content")):
            if role == "user":
                turns.append(("user", clean_user_text(chunk)))
            else:
                cleaned = clean_assistant_text(chunk)
                if cleaned:
                    turns.append(("assistant", cleaned))
    return turns


def extract_uuid(reference: str) -> str | None:
    match = CITATION_RE.search(reference)
    if match:
        return match.group(1).lower()
    match = UUID_RE.search(reference)
    if match:
        return match.group(0).lower()
    return None


def resolve_transcript_path(reference: str, cursor_home: Path) -> Path | None:
    reference = reference.strip()
    direct = Path(reference).expanduser()
    if direct.is_file() and direct.suffix == ".jsonl":
        return direct

    uuid = extract_uuid(reference)
    if not uuid:
        return None

    projects = cursor_home / "projects"
    if not projects.is_dir():
        return None

    parent_candidates: list[Path] = []
    subagent_candidates: list[Path] = []
    for path in projects.glob(f"*/agent-transcripts/**/{uuid}.jsonl"):
        if "subagents" in path.parts:
            subagent_candidates.append(path)
        else:
            parent_candidates.append(path)

    for candidate in parent_candidates:
        if candidate.parent.name.lower() == uuid:
            return candidate
    if parent_candidates:
        return parent_candidates[0]
    if subagent_candidates:
        return subagent_candidates[0]
    return None


def format_turns(turns: list[tuple[str, str]]) -> str:
    blocks: list[str] = []
    for role, text in turns:
        label = "USER" if role == "user" else "ASSISTANT"
        blocks.append(f"{label}: {text}")
    return "\n\n".join(blocks)


def group_rounds(chunks: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """One round starts at each user message; consecutive assistant lines merge."""
    rounds: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    for role, text in chunks:
        if role == "user":
            if current:
                rounds.append(current)
            current = [("user", text)]
        elif not current:
            current = [("assistant", text)]
        elif current[-1][0] == "assistant":
            prev = current[-1][1]
            current[-1] = ("assistant", f"{prev}\n\n{text}")
        else:
            current.append(("assistant", text))
    if current:
        rounds.append(current)
    return rounds


def flatten_rounds(rounds: list[list[tuple[str, str]]]) -> list[tuple[str, str]]:
    flat: list[tuple[str, str]] = []
    for round_ in rounds:
        flat.extend(round_)
    return flat


def shrink_round_assistant(
    round_: list[tuple[str, str]], max_chars: int
) -> list[tuple[str, str]]:
    body = format_turns(round_)
    if len(body) <= max_chars:
        return round_

    user = next((text for role, text in round_ if role == "user"), None)
    assistants = [text for role, text in round_ if role == "assistant"]
    merged_asst = "\n\n".join(assistants)
    marker = "...[truncated]"

    if user is None:
        label = "ASSISTANT: "
        budget = max_chars - len(label) - len(marker) - 1
        if budget <= 0:
            return [("assistant", marker)]
        tail = merged_asst[-budget:] if len(merged_asst) > budget else merged_asst
        return [("assistant", f"{tail}\n{marker}" if len(merged_asst) > budget else tail)]

    prefix = f"USER: {user}\n\nASSISTANT: "
    asst_budget = max_chars - len(prefix) - len(marker) - 1
    if asst_budget <= 0:
        return [("user", user)]
    if len(merged_asst) <= asst_budget:
        out = [("user", user)]
        if merged_asst:
            out.append(("assistant", merged_asst))
        return out
    tail = merged_asst[-asst_budget:]
    return [("user", user), ("assistant", f"{tail}\n{marker}")]


def fit_recent_rounds(
    rounds: list[list[tuple[str, str]]], max_chars: int
) -> str:
    if not rounds:
        return ""
    kept_newest_first: list[list[tuple[str, str]]] = []
    for round_ in reversed(rounds):
        trial = [round_] + kept_newest_first
        chron = list(reversed(trial))
        body = format_turns(flatten_rounds(chron))
        if len(body) <= max_chars:
            kept_newest_first = trial
        else:
            if not kept_newest_first:
                return format_turns(shrink_round_assistant(round_, max_chars))
            break
    chron = list(reversed(kept_newest_first))
    return format_turns(flatten_rounds(chron))


def collapse_turns(chunks: list[tuple[str, str]]) -> str:
    rounds = group_rounds(chunks)
    body = format_turns(flatten_rounds(rounds))
    if len(body) <= MAX_OUTPUT_CHARS:
        return body

    if len(rounds) <= KEEP_LAST_ROUNDS:
        return fit_recent_rounds(rounds, MAX_OUTPUT_CHARS)

    older = rounds[:-KEEP_LAST_ROUNDS]
    recent = rounds[-KEEP_LAST_ROUNDS:]
    user_msgs = sum(
        1 for round_ in older for role, _ in round_ if role == "user"
    )
    header = (
        f"...[earlier: {len(older)} rounds collapsed, "
        f"{user_msgs} user messages]...\n\n"
    )
    budget = MAX_OUTPUT_CHARS - len(header)
    recent_body = fit_recent_rounds(recent, budget)
    return header + recent_body


def main() -> None:
    if len(sys.argv) != 2:
        print(
            "usage: extract_transcript.py <uuid|citation|path.jsonl>",
            file=sys.stderr,
        )
        raise SystemExit(2)

    cursor_home = Path(os.environ.get("CURSOR_HOME", Path.home() / ".cursor"))
    path = resolve_transcript_path(sys.argv[1], cursor_home)
    if path is None:
        print(f"ERROR: transcript not found for: {sys.argv[1]}", file=sys.stderr)
        raise SystemExit(1)

    turns = parse_jsonl(path)
    if not turns:
        print(f"ERROR: no readable turns in {path}", file=sys.stderr)
        raise SystemExit(1)

    print(collapse_turns(turns))


if __name__ == "__main__":
    main()
