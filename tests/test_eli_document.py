"""The document check (hooks/eli-document.py), run as Claude Code runs it: a
process, the PostToolUse payload as JSON on stdin. It blocks (exit 2) a document
that is not a self-contained HTML page with visuals, and warns about the rest,
the ELI levels first.

The check asks docpin what a document is; these tests point it at nothing
(ELI_DOCUMENT_ANNOTATE="") for the docs/ fallback, or at a fake `annotate`
that records how it was called. Every silent case has a twin that warns: a
hook that never said anything would fail this suite.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "hooks" / "eli-document.py"
TEMPLATE = REPO / "skills" / "documents" / "template.html"

SVG = '<svg viewBox="0 0 10 10"><rect width="5" height="5"/></svg>'
BOTH = f'<main data-eli="lambda">{SVG}</main><dialog id="z-1" data-eli="initiate"><p>zoom</p></dialog>'
ONLY_LAMBDA = f'<main data-eli="lambda">{SVG}</main><dialog id="z-1"><p>zoom</p></dialog>'
ONLY_INITIATE = f'<main>{SVG}</main><dialog id="z-1" data-eli="initiate"><p>zoom</p></dialog>'
FLAT = f'<main>{SVG}<p>One flat page.</p></main>'


def page(body: str, top: list[str] | None = None) -> str:
    """A page whose first lines are `top`, so a test controls what sits in lines 1-5."""
    lines = (top or []) + ["<!doctype html>", '<html lang="en">', "<head><title>t</title></head>",
                           f"<body>{body}</body>", "</html>"]
    return "\n".join(lines) + "\n"


# A home of its own: a real ~/.claude/eli-off on the machine running the tests would silence
# the whole suite, and every test would then pass for the wrong reason.
HOME = tempfile.mkdtemp(prefix="eli-home-")


def hook(payload: object, *, docpin: str = "", env: dict[str, str] | None = None
         ) -> tuple[int, str | None, str]:
    """(exit code, additionalContext or None, stderr) of one run of the hook."""
    environment = {**os.environ, "ELI_DOCUMENT_ANNOTATE": docpin, "HOME": HOME}
    environment.pop("CLAUDE_PROJECT_DIR", None)   # the session running the tests may set it
    environment.update(env or {})
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    done = subprocess.run([sys.executable, str(HOOK)], check=False, input=raw, capture_output=True,
                          text=True, timeout=30, env=environment)
    assert done.returncode in (0, 2), done.stderr
    context = None
    if done.stdout.strip():
        output = json.loads(done.stdout)["hookSpecificOutput"]
        assert output["hookEventName"] == "PostToolUse"
        assert set(output) == {"hookEventName", "additionalContext"}
        context = output["additionalContext"]
    return done.returncode, context, done.stderr


def run(payload: object, *, docpin: str = "", env: dict[str, str] | None = None) -> str | None:
    """The hook's additionalContext, or None when it says nothing; it must not block."""
    code, context, stderr = hook(payload, docpin=docpin, env=env)
    assert code == 0 and stderr == "", stderr
    return context


def blocked(payload: object, **kwargs) -> str:
    """The reason the hook gives when it blocks; it must block."""
    code, context, stderr = hook(payload, **kwargs)
    assert code == 2 and context is None, (code, context)
    return stderr


def written(project: Path, relative: str, text: str, tool: str = "Write") -> dict[str, object]:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return {"hook_event_name": "PostToolUse", "tool_name": tool, "cwd": str(project),
            "tool_input": {"file_path": str(path)}}


# -- what it says ------------------------------------------------------------

def test_a_document_without_levels_warns_and_names_the_way_out(tmp_path):
    said = run(written(tmp_path, "docs/flat.html", page(FLAT)))
    assert said is not None
    assert said.startswith("flat.html: no ELI level is marked.")
    assert "eli:documents" in said and str(TEMPLATE) in said
    assert TEMPLATE.is_file()                       # the path it gives leads somewhere
    assert "<!-- eli: exemption — reason -->" in said


def test_a_document_with_both_levels_is_left_alone(tmp_path):
    assert run(written(tmp_path, "docs/model.html", page(BOTH))) is None


@pytest.mark.parametrize("body, missing", [(ONLY_LAMBDA, "initiate"), (ONLY_INITIATE, "lambda")])
def test_one_missing_level_is_named(tmp_path, body, missing):
    said = run(written(tmp_path, "docs/half.html", page(body)))
    assert said is not None
    assert said.startswith(f'half.html: no data-eli="{missing}" in it.')


@pytest.mark.parametrize("markup", [
    "<main data-eli='lambda'></main><dialog data-eli='initiate'></dialog>",
    '<MAIN DATA-ELI="Lambda"></MAIN><DIALOG Data-Eli="INITIATE"></DIALOG>',
    "<main data-eli=lambda></main><dialog data-eli=initiate></dialog>",
    '<section data-eli="lambda initiate"></section>',
    '<main data-eli="lambda"><img data-eli="initiate" src="a.png" alt="" /></main>',
])
def test_markers_are_read_as_attributes_whatever_their_spelling(tmp_path, markup):
    assert run(written(tmp_path, "docs/spelled.html", page(SVG + markup))) is None


@pytest.mark.parametrize("markup", [
    '<pre><code>&lt;main data-eli="lambda"&gt; and data-eli="initiate"</code></pre>',
    '<p>Mark the surface with data-eli="lambda" and each zoom with data-eli="initiate".</p>',
    '<!-- <main data-eli="lambda"> <dialog data-eli="initiate"> -->',
    '<main data-eli=""></main><dialog data-eli></dialog>',
    '<main data-level="lambda"></main><dialog data-eli-level="initiate"></dialog>',
])
def test_markers_quoted_in_the_text_or_misnamed_mark_nothing(tmp_path, markup):
    said = run(written(tmp_path, "docs/quoted.html", page(SVG + markup)))
    assert said is not None and said.startswith("quoted.html: no ELI level is marked.")


# -- the exemption -------------------------------------------------------------

@pytest.mark.parametrize("marker", [
    "<!-- eli: exemption — a raw transcript -->",
    "<!-- eli: exemption - raw data -->",
    "<!-- ELI : Exemption – reason -->",
    "<!-- eli : dérogation — une transcription -->",   # the French word is accepted too
    "<!-- eli: derogation - raw data -->",
    "<!-- visual: exemption - kept from visual-first -->",   # the markers of the check it replaces
    "<!-- visuel : dérogation — motif -->",
])
def test_an_exemption_in_the_first_five_lines_silences_it(tmp_path, marker):
    four_before = ["<!-- 1 -->", "<!-- 2 -->", "<!-- 3 -->", "<!-- 4 -->"]
    assert run(written(tmp_path, "docs/x.html", page(FLAT, four_before + [marker]))) is None


def test_an_exemption_on_the_sixth_line_is_too_late(tmp_path):
    five_before = ["<!-- 1 -->", "<!-- 2 -->", "<!-- 3 -->", "<!-- 4 -->", "<!-- 5 -->"]
    marker = "<!-- eli: exemption — too low -->"
    assert run(written(tmp_path, "docs/x.html", page(FLAT, five_before + [marker]))) is not None


@pytest.mark.parametrize("marker", [
    "<!-- eli: exemption -->",                         # no reason given
    "<!-- elk: exemption — reason -->",                # another check's marker
    "<!-- eli exemption — reason -->",                 # no colon
])
def test_an_exemption_without_reason_or_for_another_check_does_not_count(tmp_path, marker):
    assert run(written(tmp_path, "docs/x.html", page(FLAT, [marker]))) is not None


# -- what it covers ----------------------------------------------------------------

def test_without_docpin_a_docs_folder_decides(tmp_path):
    assert run(written(tmp_path, "docs/a.html", page(FLAT))) is not None
    assert run(written(tmp_path, "docs/sub/b.htm", page(FLAT))) is not None
    assert run(written(tmp_path, "notes/a.html", page(FLAT))) is None
    assert run(written(tmp_path, "a.html", page(FLAT))) is None


@pytest.mark.parametrize("folder", ["plans", "drafts", "brouillons", "figures", "node_modules"])
def test_working_notes_and_figure_sources_are_never_covered(tmp_path, folder):
    assert run(written(tmp_path, f"docs/{folder}/a.html", page(FLAT))) is None
    assert run(written(tmp_path, "docs/a.html", page(FLAT))) is not None   # the twin


def test_a_markdown_document_is_blocked_but_not_a_readme(tmp_path):
    said = blocked(written(tmp_path, "docs/a.md", "# A flat note\n"))
    assert said.startswith("a.md: a Markdown deliverable")
    assert "Rework it now" in said and "<!-- eli: exemption — reason -->" in said
    for name in ("README.md", "CLAUDE.md", "SKILL.md"):
        assert run(written(tmp_path, f"docs/{name}", "# Text is the deliverable\n")) is None


@pytest.mark.parametrize("tool, expected", [("Write", True), ("Edit", True), ("MultiEdit", True),
                                            ("Read", False), ("Bash", False)])
def test_only_writing_tools_are_judged(tmp_path, tool, expected):
    said = run(written(tmp_path, "docs/a.html", page(FLAT), tool=tool))
    assert (said is not None) is expected


def test_a_relative_path_is_resolved_against_the_session_folder(tmp_path):
    payload = written(tmp_path, "docs/a.html", page(FLAT))
    payload["tool_input"] = {"file_path": "docs/a.html"}
    assert run(payload) is not None


def test_the_project_folder_of_the_session_wins_over_cwd(tmp_path):
    payload = written(tmp_path / "project", "docs/a.html", page(FLAT))
    payload["cwd"] = str(tmp_path / "elsewhere")
    assert run(payload) is None
    assert run(payload, env={"CLAUDE_PROJECT_DIR": str(tmp_path / "project")}) is not None


# -- docpin decides when it is there --------------------------------------------------

def fake_annotate(folder: Path, code: int) -> tuple[Path, Path]:
    """A stand-in for `annotate` that answers like the real one (0 document, 1 not) and logs
    its arguments, so that a call of the wrong shape shows."""
    log = folder / "annotate.log"
    script = folder / "annotate"
    script.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{log}'\nexit {code}\n", encoding="utf-8")
    script.chmod(0o755)
    return script, log


def test_docpin_can_cover_a_page_outside_docs(tmp_path):
    script, log = fake_annotate(tmp_path, 0)
    payload = written(tmp_path, "reports/a.html", page(FLAT))
    assert run(payload, docpin=str(script)) is not None
    assert log.read_text(encoding="utf-8").split() == ["is-document", payload["tool_input"]["file_path"]]


def test_docpin_can_leave_out_a_page_inside_docs(tmp_path):
    script, log = fake_annotate(tmp_path, 1)
    assert run(written(tmp_path, "docs/a.html", page(FLAT)), docpin=str(script)) is None
    assert log.read_text(encoding="utf-8").startswith("is-document ")


def test_a_broken_docpin_falls_back_to_the_docs_rule(tmp_path):
    script, _ = fake_annotate(tmp_path, 3)
    assert run(written(tmp_path, "docs/a.html", page(FLAT)), docpin=str(script)) is not None
    assert run(written(tmp_path, "reports/a.html", page(FLAT)), docpin=str(script)) is None
    missing = tmp_path / "no-such-annotate"
    assert run(written(tmp_path, "docs/b.html", page(FLAT)), docpin=str(missing)) is not None


def test_docpin_is_not_asked_about_what_is_never_covered(tmp_path):
    script, log = fake_annotate(tmp_path, 0)
    assert run(written(tmp_path, "docs/plans/a.html", page(FLAT)), docpin=str(script)) is None
    assert run(written(tmp_path, "docs/README.md", "# note\n"), docpin=str(script)) is None
    assert not log.exists()


# -- it never breaks a session ------------------------------------------------------------

@pytest.mark.parametrize("raw", ["", "not json", "[]", "null", "42", '{"tool_name": "Write"}',
                                 '{"tool_name": "Write", "tool_input": {"file_path": 7}}',
                                 '{"tool_name": "Write", "tool_input": null}'])
def test_unreadable_input_says_nothing_and_exits_zero(raw):
    assert run(raw) is None


def test_a_vanished_file_says_nothing(tmp_path):
    payload = written(tmp_path, "docs/a.html", page(FLAT))
    Path(payload["tool_input"]["file_path"]).unlink()
    assert run(payload) is None


def test_a_page_that_is_not_utf8_is_still_judged(tmp_path):
    payload = written(tmp_path, "docs/a.html", "")
    Path(payload["tool_input"]["file_path"]).write_bytes(page(FLAT).encode("utf-8") + b"\xff\xfe")
    assert run(payload) is not None


# -- visuals and self-containment: what the visual-first check did --------------------------

@pytest.mark.parametrize("body", ["<main data-eli='lambda'><p>Only words.</p></main>",
                                  '<div class="mermaid">graph TD; A-->B</div>'])
def test_an_html_page_without_a_visual_is_blocked(tmp_path, body):
    said = blocked(written(tmp_path, "docs/words.html", page(body)))
    assert said.startswith("words.html: no visual in this HTML page")
    assert ("mermaid block draws nothing" in said) is ("mermaid" in body)


@pytest.mark.parametrize("visual", ['<svg viewBox="0 0 1 1"></svg>', '<img src="a.png" alt="">',
                                    "<canvas></canvas>", "<table><tr><td>1</td></tr></table>"])
def test_each_kind_of_visual_counts(tmp_path, visual):
    body = f'<main data-eli="lambda">{visual}</main><dialog data-eli="initiate"></dialog>'
    assert run(written(tmp_path, "docs/v.html", page(body))) is None


def test_a_page_that_loads_from_the_network_warns(tmp_path):
    body = BOTH + '<script src="https://cdn.example.org/lib.js"></script>'
    said = run(written(tmp_path, "docs/net.html", page(body)))
    assert said is not None and "loads from the network: https://cdn.example.org/lib.js" in said


def test_more_than_four_paragraphs_per_visual_warns(tmp_path):
    assert run(written(tmp_path, "docs/p.html", page(BOTH + "<p>x</p>" * 3))) is None   # BOTH holds one already
    said = run(written(tmp_path, "docs/p.html", page(BOTH + "<p>x</p>" * 4)))
    assert said is not None and "5 paragraphs for 1 visual(s)" in said


def test_a_heavy_image_warns_until_git_tracks_it(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "big.png").write_bytes(b"0" * 1_000_001)
    body = BOTH + '<img src="big.png" alt="">'
    said = run(written(tmp_path, "docs/i.html", page(body)))
    assert said is not None and "big.png weighs 1.0 MB" in said
    subprocess.run(["git", "-C", str(tmp_path), "add", "docs/big.png"], check=True)
    assert run(written(tmp_path, "docs/i.html", page(body))) is None


def test_the_off_switch_silences_it_and_only_it_does(tmp_path):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    payload = written(tmp_path, "docs/a.md", "# note\n")
    assert blocked(payload, env={"HOME": str(home)})
    (home / ".claude" / "eli-off").touch()
    assert run(payload, env={"HOME": str(home)}) is None


# -- the template of the eli:documents skill ---------------------------------------------------

def test_the_template_written_as_a_document_is_left_alone(tmp_path):
    target = tmp_path / "docs" / "2026-10-23-subject.html"
    target.parent.mkdir()
    shutil.copy(TEMPLATE, target)
    payload = {"hook_event_name": "PostToolUse", "tool_name": "Write", "cwd": str(tmp_path),
               "tool_input": {"file_path": str(target)}}
    assert run(payload) is None
    # The twin: the same page with its markers renamed warns, so the silence above comes
    # from the markers and not from an exemption or from the page not being covered.
    target.write_text(TEMPLATE.read_text(encoding="utf-8").replace("data-eli=", "data-was="),
                      encoding="utf-8")
    assert run(payload) is not None
