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
import re
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
# No <p> in it: the paragraph count stays the one each test sets.
TLDR = '<section data-tldr><b>TL;DR</b> what was found, and what applies without an answer.</section>'
BOTH = f'<main data-eli="lambda">{TLDR}{SVG}</main><dialog id="z-1" data-eli="initiate"><p>zoom</p></dialog>'
ONLY_LAMBDA = f'<main data-eli="lambda">{TLDR}{SVG}</main><dialog id="z-1"><p>zoom</p></dialog>'
ONLY_INITIATE = f'<main>{TLDR}{SVG}</main><dialog id="z-1" data-eli="initiate"><p>zoom</p></dialog>'
FLAT = f'<main>{TLDR}{SVG}<p>One flat page.</p></main>'


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
    assert run(written(tmp_path, "docs/spelled.html", page(TLDR + SVG + markup))) is None


@pytest.mark.parametrize("markup", [
    '<pre><code>&lt;main data-eli="lambda"&gt; and data-eli="initiate"</code></pre>',
    '<p>Mark the surface with data-eli="lambda" and each zoom with data-eli="initiate".</p>',
    '<!-- <main data-eli="lambda"> <dialog data-eli="initiate"> -->',
    '<main data-eli=""></main><dialog data-eli></dialog>',
    '<main data-level="lambda"></main><dialog data-eli-level="initiate"></dialog>',
])
def test_markers_quoted_in_the_text_or_misnamed_mark_nothing(tmp_path, markup):
    said = run(written(tmp_path, "docs/quoted.html", page(TLDR + SVG + markup)))
    assert said is not None and said.startswith("quoted.html: no ELI level is marked.")


@pytest.mark.parametrize("markup", ["<div data-tldr></div>", "<P DATA-TLDR=''>x</P>",
                                    '<section data-tldr="yes">x</section>'])
def test_a_tldr_is_an_attribute_whatever_its_spelling(tmp_path, markup):
    body = BOTH.replace(TLDR, markup)
    assert run(written(tmp_path, "docs/t.html", page(body))) is None


@pytest.mark.parametrize("markup", ["", "<p>TL;DR: what was found.</p>",
                                    "<pre><code>&lt;section data-tldr&gt;</code></pre>",
                                    "<!-- <section data-tldr> -->", '<div class="tldr">x</div>'])
def test_a_document_without_a_tldr_warns_and_says_what_it_holds(tmp_path, markup):
    said = run(written(tmp_path, "docs/t.html", page(BOTH.replace(TLDR, markup))))
    assert said is not None and said.startswith("t.html: no TL;DR (an element with data-tldr)")
    assert "what applies without an answer" in said


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
    body = f'<main data-eli="lambda">{TLDR}{visual}</main><dialog data-eli="initiate"></dialog>'
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
    target.write_text(TEMPLATE.read_text(encoding="utf-8").replace("data-tldr", "data-was"),
                      encoding="utf-8")
    said = run(payload)
    assert said is not None and "no TL;DR" in said
    target.write_text(TEMPLATE.read_text(encoding="utf-8").replace("data-def=", "data-was="),
                      encoding="utf-8")
    assert listed(run(payload)) == ["API"]      # the abbreviation it shows, defined by a term


# -- an eli figure is a visual ------------------------------------------------------------------

FIGURE = ('<figure data-figure="chain"><ol class="f-chain"><li data-node="action">You ask</li>'
          '<li class="f-to" aria-hidden="true"></li><li data-node="result">It answers</li></ol></figure>')


def test_an_eli_figure_counts_as_a_visual(tmp_path):
    body = f'<main data-eli="lambda">{TLDR}{FIGURE}</main><dialog data-eli="initiate"></dialog>'
    assert "<svg" not in body and "<table" not in body
    assert run(written(tmp_path, "docs/f.html", page(body))) is None


@pytest.mark.parametrize("old, new", [('data-figure="chain"', 'data-fig="chain"'),
                                      ('data-figure="chain"', 'data-figure=""'),
                                      (FIGURE, '<pre><code>&lt;figure data-figure="chain"&gt;</code></pre>')])
def test_a_misnamed_empty_or_quoted_figure_is_no_visual(tmp_path, old, new):
    body = f'<main data-eli="lambda">{TLDR}{FIGURE}</main><dialog data-eli="initiate"></dialog>'
    said = blocked(written(tmp_path, "docs/f.html", page(body.replace(old, new))))
    assert said.startswith("f.html: no visual in this HTML page") and "data-figure" in said


# -- the surface fits in SURFACE_MAX_WORDS ------------------------------------------------------

def surface(words: int, extra: str = "") -> str:
    """A page whose surface shows `words` words (the TL;DR's included) and holds `extra`."""
    tldr_words = len(re.sub(r"<[^>]+>", " ", TLDR).split())     # the words the TL;DR shows
    filler = " ".join(f"w{i}" for i in range(words - tldr_words))
    return page(f'<main data-eli="lambda">{TLDR}{SVG}<span>{filler}</span>{extra}</main>'
                '<dialog data-eli="initiate"><p>zoom</p></dialog>')


def test_a_surface_of_300_words_is_left_alone_and_301_warns_with_its_count(tmp_path):
    assert run(written(tmp_path, "docs/s.html", surface(300))) is None
    said = run(written(tmp_path, "docs/s.html", surface(301)))
    assert said is not None and said.startswith('s.html: the surface (data-eli="lambda") holds 301 words, over 300')
    assert "move the rest down into the zooms" in said


FIFTY = " ".join(f"x{i}" for i in range(50))
HIDDEN_FROM_THE_SURFACE = [
    f'<div data-eli="initiate">{FIFTY}</div>',                       # another level
    f'<section data-eli="architect"><p>{FIFTY}</p></section>',
    f"<style>.a{{}} /* {FIFTY} */</style>", f"<script>// {FIFTY}</script>",
    f"<div hidden>{FIFTY}</div>", f"<dialog><p>{FIFTY}</p></dialog>",   # not shown
    f"<details><summary></summary><p>{FIFTY}</p></details>",
    "→ · — ✓ " * 20,                                                   # no word in them
    ": ? ! ; « » – _ " * 10,                                           # punctuation alone
]


@pytest.mark.parametrize("extra", HIDDEN_FROM_THE_SURFACE)
def test_what_the_surface_does_not_show_is_not_counted(tmp_path, extra):
    assert run(written(tmp_path, "docs/s.html", surface(300, extra))) is None


@pytest.mark.parametrize("extra", [f"<div>{FIFTY}</div>", f'<div data-eli="lambda">{FIFTY}</div>',
                                   f"<dialog open><p>{FIFTY}</p></dialog>",
                                   f"<details open><summary></summary><p>{FIFTY}</p></details>",
                                   f"<details><summary>{FIFTY}</summary><p>hidden</p></details>"])
def test_what_the_surface_shows_is_counted(tmp_path, extra):
    said = run(written(tmp_path, "docs/s.html", surface(300, extra)))
    assert said is not None and "holds 350 words, over 300" in said


# -- abbreviations are explained where they are used --------------------------------------------------

def jargon(prose: str, extra: str = "") -> str:
    return page(f'<main data-eli="lambda">{TLDR}{SVG}<p>{prose}</p>{extra}</main>'
                '<dialog data-eli="initiate"><p>zoom</p></dialog>')


def listed(said: str | None) -> list[str]:
    """The abbreviations a warning lists, or [] when it lists none."""
    if said is None or "abbreviation(s) that nothing in the page explains: " not in said:
        return []
    return said.split("abbreviation(s) that nothing in the page explains: ")[1].split(". ")[0].split(", ")


SENTENCE = "The HUD reads MIDI notes through an API, then an LLM writes the plan."


def test_undefined_abbreviations_are_listed_with_the_way_to_explain_them(tmp_path):
    said = run(written(tmp_path, "docs/j.html", jargon(SENTENCE)))
    assert listed(said) == ["HUD", "MIDI", "API", "LLM"]
    assert "4 abbreviation(s)" in said and 'data-def="what it means"' in said and "<abbr" in said


DEFINITIONS = {
    "HUD": '<span class="term" tabindex="0" data-def="Heads-up display: a panel over the screen">HUD</span>',
    "MIDI": '<abbr title="Musical Instrument Digital Interface">MIDI</abbr>',
    "API": '<span class="term" tabindex="0" data-def="The door a program opens to another">APIs</span>',
    "LLM": '<span class="term" tabindex="0" data-def="Large language model">the LLM</span>',
}


@pytest.mark.parametrize("word", DEFINITIONS)
def test_an_abbreviation_defined_once_is_no_longer_listed(tmp_path, word):
    said = run(written(tmp_path, "docs/j.html", jargon(SENTENCE, f"<p>{DEFINITIONS[word]}</p>")))
    assert listed(said) == [w for w in ("HUD", "MIDI", "API", "LLM") if w != word]


def test_all_defined_the_page_is_left_alone(tmp_path):
    extra = "".join(f"<span>{d}</span>" for d in DEFINITIONS.values())   # no <p>: no prose count
    assert run(written(tmp_path, "docs/j.html", jargon(SENTENCE + " The HUD again.", extra))) is None


@pytest.mark.parametrize("definition", ['<span data-def="">HUD</span>', '<span data-def>HUD</span>',
                                        "<abbr>HUD</abbr>", '<abbr title=" ">HUD</abbr>',
                                        '<span title="Heads-up display">HUD</span>'])
def test_an_empty_or_misplaced_definition_defines_nothing(tmp_path, definition):
    said = run(written(tmp_path, "docs/j.html", jargon("The HUD shows it.", f"<p>{definition}</p>")))
    assert listed(said) == ["HUD"]


@pytest.mark.parametrize("prose", [
    "<code>HUD</code> and <pre>MIDI</pre> and <kbd>API</kbd> and <samp>LLM</samp>",   # code is code
    "OK, a PDF at a URL on a USB key. TL;DR: ELI5, then ELI-lambda.",                # common words
    "NEVER do that, never. DO NOT REMOVE IT. Then PLEASE see EX-R-04, PR-02, NOTES.md, phase II.",
])
def test_code_common_words_emphasis_ids_and_files_are_never_listed(tmp_path, prose):
    said = run(written(tmp_path, "docs/j.html", jargon(prose + " The HUD.")))
    assert listed(said) == ["HUD"]     # the witness: the same page does list an abbreviation


def test_a_long_list_of_abbreviations_is_cut_and_counted(tmp_path):
    words = ["AAB", "BBC", "CCD", "DDE", "EEF", "FFG", "GGH", "HHJ", "JJK", "KKL", "LLM", "MMN", "NNP", "PPQ"]
    said = run(written(tmp_path, "docs/j.html", jargon(" and ".join(words))))
    assert listed(said) == [*words[:11], "MMN and 2 more"] and "14 abbreviation(s)" in said
