#!/usr/bin/env python3
"""PostToolUse hook: send the session back to a document it just wrote, when the
document is not what the eli style asks for — a self-contained HTML page, drawn
before it is written, that opens on an ELI-lambda surface whose elements zoom into
ELI-initiate (form and template: the `eli:documents` skill).

The file is already on disk when this runs: a block does not prevent it, it makes
the session rework it BEFORE moving on, which prose instructions alone did not
obtain.

| The document                                                     | Verdict |
|------------------------------------------------------------------|---------|
| a Markdown deliverable                                           | block: a document is a self-contained HTML page |
| an HTML page without any visual (svg, img, canvas, table, or an element carrying `data-figure`) | block |
| no `data-eli="lambda"` surface or no `data-eli="initiate"` zoom  | warning |
| no TL;DR: no element carrying `data-tldr`                         | warning |
| a script, stylesheet or image loaded from the network            | warning: not self-contained |
| a surface over SURFACE_MAX_WORDS words                           | warning: move the rest down a level |
| an abbreviation that nothing in the page defines                 | warning, listing them |
| more than PROSE_PER_VISUAL paragraphs per visual                 | warning |
| a local image over 1 MB that git does not track yet              | warning |
| `<!-- eli: exemption — reason -->` in its first five lines       | nothing |

A missing level warns and never blocks: it does not make a document wrong, and two
blocks on one file would mean two reworks for one fault. A `class="mermaid"` block
is not a visual: it draws nothing without its library, which a self-contained page
does not load. Levels, figures and definitions are read from tag attributes
(html.parser), never from the text: a page that quotes `data-eli="lambda"` in a code
sample marks nothing.

The surface is the text a reader sees in the `data-eli="lambda"` element: a word is
a run of characters holding a letter or a digit; style, script, a subtree of another
level, and what is hidden (`hidden`, a closed `dialog`, a closed `details` past its
summary) are left out. An abbreviation is a word of 2 to 5 capitals, digits allowed
after the first (`HUD`, `VST3`, plural `APIs`); it is defined when it appears in the
text of an element carrying `data-def` or of an `abbr` with a `title`, anywhere in
the page. Never counted: what sits in `code`, `pre`, `kbd` or `samp`;
COMMON_ABBREVIATIONS and `TL;DR`; a word the page also writes in lower case (`NEVER`
beside `never`: emphasis); words in capitals in a row when one of them cannot be an
abbreviation, being over five letters or accented (a heading, a shout); an id
(`EX-R-04`, `PR-02`), a file name (`CLAUDE.md`), Roman numerals.

What is a document is decided by docpin when it is installed (`annotate
is-document <path>`, through `annotate` on the PATH or docpin's stable copy: the
folders the user tracks there); without it, by a `docs/` folder between the
project and the file. READMEs, `CLAUDE.md`, skills, dependencies, working notes
(`plans/`, `drafts/`) and figure sources (`figures/`) are never covered.
`ELI_DOCUMENT_ANNOTATE` overrides the docpin command (an empty value means: no
docpin), for the tests.

It never exits other than 0 or 2: a failure of this hook must not break a session.
`~/.claude/eli-off` turns it off for the machine.
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
SUFFIXES = {".md", ".html", ".htm"}
EXCLUDED_NAMES = {"README.md", "CHANGELOG.md", "CONTRIBUTING.md", "CLAUDE.md", "AGENTS.md",
                  "LICENSE.md", "SKILL.md"}
# Working notes are Markdown on purpose ("brouillons": the same, in French).
EXCLUDED_FOLDERS = {"node_modules", ".venv", "venv", "site-packages", ".git", "__pycache__",
                    "plans", "drafts", "brouillons", "figures"}
REQUIRED = ("lambda", "initiate")
EXEMPTION_LINES = 5
PROSE_PER_VISUAL = 4
IMAGE_MAX_BYTES = 1_000_000
SURFACE_MAX_WORDS = 300
# Abbreviations a reader of any background knows. ELI is this plugin's own vocabulary
# (ELI5, ELI-lambda...), which every document made from its template carries.
COMMON_ABBREVIATIONS = {"OK", "PDF", "URL", "USB", "ELI", "AI", "IA", "ID", "PC", "FAQ",
                        "KB", "MB", "GB", "TB"}
ABBREVIATIONS_SHOWN = 12

# The eli marker, and the markers of the visual-first check it replaces (English and
# French), so that a page exempted there stays exempted here.
_EXEMPTION = re.compile(r"^\s*<!--\s*(?:eli\s*:\s*(?:exemption|d[ée]rogation)|visual\s*:\s*exemption"
                        r"|visuel\s*:\s*d[ée]rogation)\s*[—–-]\s*(.+?)\s*-->\s*$", re.IGNORECASE)
_FIGURE = re.compile(r"<(?:svg|img|canvas|table)\b", re.IGNORECASE)
_MERMAID = re.compile(r"class\s*=\s*[\"'][^\"']*\bmermaid\b", re.IGNORECASE)
_EXTERNAL = re.compile(r"<(?:script|img|link|iframe)\b[^>]*?\b(?:src|href)\s*=\s*[\"']"
                       r"((?:https?:)?//[^\"']+)", re.IGNORECASE)
_PARAGRAPH = re.compile(r"<p\b", re.IGNORECASE)
_LOCAL_IMAGE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"'#?:]+)[\"']", re.IGNORECASE)
# 2 to 5 capitals (digits allowed after the first), an optional plural; not glued to a
# word, not a file name (CLAUDE.md), not an id (EX-R-04, PR-02).
_ABBREVIATION = re.compile(r"(?<![\w.-])([A-Z][A-Z0-9]{1,6})(?:s|['\u2019]s)?"
                           r"(?![\w]|\.\w|-[A-Z]*\d|-[A-Z]+-)")
_ROMAN = re.compile(r"[IVX]+")
_LETTERS = re.compile(r"[^\W\d_]")
_WORD = re.compile(r"[^\W\d_]+")
_LETTER_OR_DIGIT = re.compile(r"[^\W_]")
# Text that is code, not prose: an abbreviation in it is never counted.
_CODE_TAGS = {"code", "pre", "kbd", "samp"}
_NO_TEXT_TAGS = {"script", "style", "template", "noscript", "title"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
         "source", "track", "wbr"}

TEMPLATE = Path(__file__).resolve().parents[1] / "skills" / "documents" / "template.html"
FIX = ("write it as a self-contained HTML page that draws what can be drawn (SVG, diagram, "
       "table) and follows the ELI model: an ELI-lambda surface (data-eli=\"lambda\") whose "
       "elements open ELI-initiate zooms (data-eli=\"initiate\"), each leading down to "
       f"ELI-Architect. Use the eli:documents skill and its template {TEMPLATE}")
EXEMPT = ("If the form is justified (a transcript, raw data), put "
          "<!-- eli: exemption — reason --> in its first five lines")


class _Open:
    """An element still open while the page is read, with what the reading needs of it."""

    def __init__(self, tag: str, attrs: dict[str, str | None]) -> None:
        self.tag = tag
        self.levels = set((attrs.get("data-eli") or "").lower().split())
        self.defines = bool((attrs.get("data-def") or "").strip()) or (
            tag == "abbr" and bool((attrs.get("title") or "").strip()))
        self.hidden = "hidden" in attrs or (tag in ("dialog", "details") and "open" not in attrs)


class _Markers(HTMLParser):
    """Collects the values of every `data-eli` attribute, whether a `data-tldr`
    attribute is there, the elements carrying `data-figure`, the words of the
    surface, and the prose text with the part of it that defines a term. A
    self-closing tag (`<img data-eli="…" />`) reaches handle_starttag through
    HTMLParser's own handle_startendtag, which then closes it."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found: set[str] = set()
        self.tldr = False
        self.figures = 0
        self.surface_words = 0
        self.prose: list[str] = []
        self.defined: list[str] = []
        self.open: list[_Open] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name == "data-eli" and value:
                self.found.update(value.lower().split())
            elif name == "data-tldr":
                self.tldr = True
            elif name == "data-figure" and (value or "").strip():
                self.figures += 1
        if tag not in _VOID:
            self.open.append(_Open(tag, dict(attrs)))

    def handle_endtag(self, tag: str) -> None:
        for depth in range(len(self.open) - 1, -1, -1):
            if self.open[depth].tag == tag:
                del self.open[depth:]
                return

    def _shown(self) -> bool:
        """Whether text here shows without a click: a closed details shows its summary."""
        for depth, element in enumerate(self.open):
            if element.hidden and not (element.tag == "details" and any(
                    inner.tag == "summary" for inner in self.open[depth + 1:])):
                return False
        return True

    def handle_data(self, data: str) -> None:
        tags = {element.tag for element in self.open}
        if tags & _NO_TEXT_TAGS:
            return
        level = next((element.levels for element in reversed(self.open) if element.levels), set())
        if "lambda" in level and self._shown():
            # a word holds a letter or a digit: a lone ":", "?", dash or "_" is not one
            self.surface_words += sum(1 for word in data.split() if _LETTER_OR_DIGIT.search(word))
        if tags & _CODE_TAGS:
            return
        self.prose.append(data)
        if any(element.defines for element in self.open):
            self.defined.append(data)


def _markers(text: str) -> _Markers:
    parser = _Markers()
    parser.feed(text)
    parser.close()
    return parser


def _shouted(text: str) -> list[tuple[int, int]]:
    """The spans of words in capitals that are not abbreviations: two or more such
    words in a row, one of which cannot be an abbreviation (over five letters, or a
    letter outside A-Z: `DO NOT REMOVE`). A word with no letter does not break a run."""
    spans, run = [], []
    for token in [*re.finditer(r"\S+", text), None]:
        letters = _LETTERS.findall(token.group()) if token else ["end"]
        if token and letters and token.group().upper() == token.group():
            run.append((token, len(letters) > 5 or any(not "A" <= c <= "Z" for c in letters)))
        elif letters:
            if len(run) >= 2 and any(plain for _, plain in run):
                spans.append((run[0][0].start(), run[-1][0].end()))
            run = []
    return spans


def _abbreviations_in(text: str) -> list[str]:
    """The abbreviations of a text, in order of appearance, with the exclusions of the
    module docstring applied; one entry per occurrence."""
    text = text.replace("TL;DR", " ")
    lower = {word.lower() for word in _WORD.findall(text) if not word.isupper()}
    shouted = _shouted(text)
    found = []
    for match in _ABBREVIATION.finditer(text):
        word = match.group(1)
        base = word.rstrip("0123456789")
        if not 2 <= len(_LETTERS.findall(word)) <= 5 or _ROMAN.fullmatch(word):
            continue
        if {word, base} & COMMON_ABBREVIATIONS or {word.lower(), base.lower()} & lower:
            continue
        if any(start <= match.start() < end for start, end in shouted):
            continue
        found.append(word)
    return found


def undefined_abbreviations(markers: _Markers) -> list[str]:
    """The abbreviations of the page that nothing in it defines, in order of first use;
    `VST` defined covers `VST3`, and the other way round."""
    defined = set()
    for word in _abbreviations_in(" ".join(markers.defined)):
        defined.update({word, word.rstrip("0123456789")})
    used = _abbreviations_in(" ".join(markers.prose))
    return [word for word in dict.fromkeys(used)
            if word not in defined and word.rstrip("0123456789") not in defined]


def levels(text: str) -> set[str]:
    return _markers(text).found


def has_tldr(text: str) -> bool:
    return _markers(text).tldr


def exemption(text: str) -> str | None:
    for line in text.splitlines()[:EXEMPTION_LINES]:
        found = _EXEMPTION.match(line)
        if found:
            return found.group(1)
    return None


def missing_levels(text: str) -> str | None:
    found = levels(text)
    missing = [level for level in REQUIRED if level not in found]
    if not missing:
        return None
    if len(missing) == len(REQUIRED):
        return "no ELI level is marked"
    return "no " + ", ".join(f'data-eli="{level}"' for level in missing) + " in it"


def _tracked_by_git(path: Path) -> bool:
    try:
        return subprocess.run(["git", "-C", str(path.parent), "ls-files", "--error-unmatch",
                               "--", path.name], capture_output=True, timeout=5,
                              check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def heavy_images(text: str, folder: Path) -> list[tuple[str, int]]:
    """Local images over IMAGE_MAX_BYTES that git does not track yet: a new one is
    said when the document references it, a committed one is left."""
    found = []
    for src in dict.fromkeys(_LOCAL_IMAGE.findall(text)):
        image = folder / src
        try:
            size = image.stat().st_size
        except OSError:
            continue
        if size > IMAGE_MAX_BYTES and not _tracked_by_git(image):
            found.append((src, size))
    return found


def verdict(path: Path, text: str) -> tuple[str, str]:
    """("ok" | "warning" | "block" | "exempt", reason) for a covered document."""
    reason = exemption(text)
    if reason:
        return "exempt", reason
    if path.suffix.lower() == ".md":
        return "block", ("a Markdown deliverable: a document is a self-contained HTML page, "
                         "with as many visuals as it has ideas to show")
    markers = _markers(text)
    figures = len(_FIGURE.findall(text)) + markers.figures
    if figures == 0:
        mermaid = (" (a mermaid block draws nothing without its library: draw it as inline "
                   "SVG or an eli figure)") if _MERMAID.search(text) else ""
        return "block", ("no visual in this HTML page: a document is drawn (svg, img, table, "
                         f"canvas, an eli figure with data-figure) before it is written{mermaid}")
    reasons = []
    unmarked = missing_levels(text)
    if unmarked:
        reasons.append(unmarked)
    if not has_tldr(text):
        reasons.append("no TL;DR (an element with data-tldr): open the surface on one to three "
                       "sentences that are enough by themselves, each decision with its "
                       "problem, its recommendation and what applies without an answer")
    external = list(dict.fromkeys(_EXTERNAL.findall(text)))
    if external:
        shown = ", ".join(external[:3]) + (" ..." if len(external) > 3 else "")
        reasons.append(f"not self-contained, it loads from the network: {shown}")
    if markers.surface_words > SURFACE_MAX_WORDS:
        reasons.append(f"the surface (data-eli=\"lambda\") holds {markers.surface_words} words, "
                       f"over {SURFACE_MAX_WORDS}: keep on it the promise, the TL;DR and one "
                       "sentence per element, and move the rest down into the zooms")
    undefined = undefined_abbreviations(markers)
    if undefined:
        listed = ", ".join(undefined[:ABBREVIATIONS_SHOWN])
        more = len(undefined) - ABBREVIATIONS_SHOWN
        listed += f" and {more} more" if more > 0 else ""
        reasons.append(f"{len(undefined)} abbreviation(s) that nothing in the page explains: {listed}. "
                       "Explain each one where it first appears, as <span class=\"term\" "
                       "tabindex=\"0\" data-def=\"what it means\">HUD</span> (or <abbr "
                       "title=\"...\">), or write the plain words instead")
    paragraphs = len(_PARAGRAPH.findall(text))
    if paragraphs > PROSE_PER_VISUAL * figures:
        reasons.append(f"{paragraphs} paragraphs for {figures} visual(s), more than "
                       f"{PROSE_PER_VISUAL} per visual: draw the rest")
    for src, size in heavy_images(text, path.parent):
        reasons.append(f"{src} weighs {size / 1e6:.1f} MB, over {IMAGE_MAX_BYTES / 1e6:.0f} MB: "
                       f"render it smaller")
    return ("warning", "; ".join(reasons)) if reasons else ("ok", "")


def _docpin_command() -> tuple[list[str], dict[str, str]] | None:
    """How to ask docpin: `annotate` on the PATH, else the stable copy docpin's
    plugin keeps in its data folder. A plugin hook does not get another plugin's
    bin/ on its PATH, so the copy is what it usually finds."""
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
    if path.suffix.lower() not in SUFFIXES or path.name in EXCLUDED_NAMES:
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
        if (Path.home() / ".claude" / "eli-off").exists():
            return 0
        raw = (payload.get("tool_input") or {}).get("file_path")
        if not isinstance(raw, str) or not raw:
            return 0
        cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else ""
        project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or cwd or ".")
        path = Path(raw) if Path(raw).is_absolute() else project / raw
        if not covered(path, project):
            return 0
        status, reason = verdict(path, path.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001 - a broken check must never break the session
        return 0
    if status == "block":
        print(f"{path.name}: {reason}.\nRework it now, before anything else: {FIX}.\n"
              f"{EXEMPT}.", file=sys.stderr)
        return 2
    if status == "warning":
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": f"{path.name}: {reason}. Rework it before moving on: {FIX}. "
                                 f"{EXEMPT}.",
        }}))  # ASCII-escaped: a hook's stdout encoding is not guaranteed to be UTF-8
    return 0


if __name__ == "__main__":
    sys.exit(main())
