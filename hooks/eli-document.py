#!/usr/bin/env python3
"""PostToolUse hook: warn the session when a document it just wrote does not
follow the ELI model (explanation levels).

The model: a document opens on an ELI-lambda surface (`data-eli="lambda"`)
whose elements open ELI-initiate zooms (`data-eli="initiate"`), each zoom
leading down to ELI-Architect, with occasional ELI-Tech inserts. Form and
template: the `eli:documents` skill.

| The file                                                   | Verdict |
|------------------------------------------------------------|---------|
| not a document (see below), or not an .html / .htm page    | nothing |
| a document that marks both the lambda and initiate levels  | nothing |
| a document missing one of them, or both                    | warning naming what is missing |
| `<!-- eli: exemption — reason -->` in its first five lines   | nothing |

A warning, never a block: a missing level does not make a document wrong, and
a check that blocks makes the session rework a page that may be right (docpin's
visual-first check, when installed, already blocks a document without visuals;
two blocks on one file would mean two reworks for one fault). Markdown
documents are not judged: the HTML page they become is.

Levels are read from tag attributes (html.parser), never from the text: a page
that quotes `data-eli="lambda"` in a code sample marks nothing.

What is a document is decided as docpin's visual-first check decides it: by
docpin when it is installed (`annotate is-document <path>`, through `annotate` on the PATH or
docpin's stable copy), otherwise by a `docs/` folder between the project and
the file. Working notes (`plans/`, `drafts/`) and figure sources
(`figures/`) are never covered. `ELI_DOCUMENT_ANNOTATE` overrides the docpin
command (an empty value means: no docpin), for the tests.

It always exits 0: a failure of this hook must never break a session.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

TOOLS = {"Write", "Edit", "MultiEdit"}
SUFFIXES = {".html", ".htm"}
EXCLUDED_FOLDERS = {"node_modules", ".venv", "venv", "site-packages", ".git", "__pycache__",
                    "plans", "drafts", "figures"}
REQUIRED = ("lambda", "initiate")
EXEMPTION_LINES = 5

_EXEMPTION = re.compile(r"^\s*<!--\s*eli\s*:\s*(?:d[ée]rogation|exemption)\s*[—–-]\s*(.+?)\s*-->\s*$",
                        re.IGNORECASE)

TEMPLATE = Path(__file__).resolve().parents[1] / "skills" / "documents" / "template.html"
FIX = ("documents follow the ELI model: an ELI-lambda surface (data-eli=\"lambda\") whose "
       "elements open ELI-initiate zooms (data-eli=\"initiate\"), each leading down to "
       f"ELI-Architect. Rework it with the eli:documents skill and its template {TEMPLATE}")
EXEMPT = ("If a single-level page is justified (a transcript, raw data), put "
          "<!-- eli: exemption — reason --> in its first five lines")


class _Levels(HTMLParser):
    """Collects the values of every `data-eli` attribute. A self-closing tag
    (`<img data-eli="…" />`) reaches handle_starttag through HTMLParser's own
    handle_startendtag."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "data-eli" and value:
                self.found.update(value.lower().split())


def levels(text: str) -> set[str]:
    parser = _Levels()
    parser.feed(text)
    parser.close()
    return parser.found


def exemption(text: str) -> str | None:
    for line in text.splitlines()[:EXEMPTION_LINES]:
        found = _EXEMPTION.match(line)
        if found:
            return found.group(1)
    return None


def missing_levels(text: str) -> list[str]:
    found = levels(text)
    return [level for level in REQUIRED if level not in found]


def verdict(text: str) -> tuple[str, str]:
    """("exempt" | "ok" | "warning", reason) for a covered document."""
    reason = exemption(text)
    if reason:
        return "exempt", reason
    missing = missing_levels(text)
    if not missing:
        return "ok", ""
    if len(missing) == len(REQUIRED):
        return "warning", "no ELI level is marked"
    shown = ", ".join(f'data-eli="{level}"' for level in missing)
    return "warning", f"no {shown} in it"


def _docpin_command() -> tuple[list[str], dict[str, str]] | None:
    """How to ask docpin: `annotate` on the PATH, else the stable copy docpin's
    plugin keeps in its data folder. A hook declared in settings.json does not
    get a plugin's bin/ on its PATH, so the copy is what it usually finds."""
    env = dict(os.environ)
    command = os.environ.get("ELI_DOCUMENT_ANNOTATE")
    if command is not None:
        return ([command], env) if command else None
    found = shutil.which("annotate")
    if found:
        return [found], env
    data = Path(os.environ.get("ANNOTATE_DATA_DIR")
                or Path.home() / ".local" / "share" / "annotate")
    copy = data / "runtime" / "current"
    if (copy / "annotate" / "cli.py").is_file():
        return [sys.executable, "-P", "-m", "annotate"], {**env, "PYTHONPATH": str(copy)}
    return None


def _docpin_says(path: Path) -> bool | None:
    found = _docpin_command()
    if found is None:
        return None
    command, env = found
    try:
        done = subprocess.run([*command, "is-document", str(path)], capture_output=True,
                              text=True, timeout=10, check=False, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    return {0: True, 1: False}.get(done.returncode)


def covered(path: Path, project: Path) -> bool:
    if path.suffix.lower() not in SUFFIXES:
        return False
    if EXCLUDED_FOLDERS.intersection(path.parts):
        return False
    answer = _docpin_says(path)
    if answer is not None:
        return answer
    try:
        inside = path.resolve().relative_to(project.resolve()).parts[:-1]
    except ValueError:
        return False
    return "docs" in inside


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or payload.get("tool_name") not in TOOLS:
            return 0
        raw = (payload.get("tool_input") or {}).get("file_path")
        if not isinstance(raw, str) or not raw:
            return 0
        cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else ""
        project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or cwd or ".")
        path = Path(raw) if Path(raw).is_absolute() else project / raw
        if not covered(path, project):
            return 0
        status, reason = verdict(path.read_text(encoding="utf-8", errors="replace"))
        if status == "warning":
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": f"{path.name}: {reason}. Not blocking, but {FIX}. {EXEMPT}.",
            }}))  # ASCII-escaped: a hook's stdout encoding is not guaranteed to be UTF-8
    except Exception:  # noqa: BLE001 - a broken check must never break the session
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
