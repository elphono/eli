"""The pieces of the plugin that are not the hook: the template of the
eli:documents skill, the output style and the manifests that ship them.

The template is parsed into a tree (html.parser, no dependency): a regular
expression would count a marker quoted in a comment, which is the mistake the
hook itself is built to avoid.
"""
from __future__ import annotations

import ast
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "skills" / "documents" / "template.html"
SKILL = REPO / "skills" / "documents" / "SKILL.md"
STYLE = REPO / "output-styles" / "eli.md"
HOOK = REPO / "hooks" / "eli-document.py"
HOOKS = REPO / "hooks" / "hooks.json"
PLUGIN = REPO / ".claude-plugin" / "plugin.json"
MARKETPLACE = REPO / ".claude-plugin" / "marketplace.json"

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
        "track", "wbr"}


class Node:
    def __init__(self, tag: str, attrs: dict[str, str | None], parent: Node | None) -> None:
        self.tag, self.attrs, self.parent, self.children = tag, attrs, parent, []

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def ancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def eli(self) -> set[str]:
        return set((self.attrs.get("data-eli") or "").lower().split())


class Tree(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.current = self.root
        self.script = ""

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.current)
        self.current.children.append(node)
        if tag not in VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(Node(tag, dict(attrs), self.current))

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        assert node is not self.root, f"</{tag}> closes nothing"
        self.current = node.parent

    def handle_data(self, data):
        if self.current.tag == "script":
            self.script += data


@pytest.fixture(scope="module")
def template():
    tree = Tree()
    tree.feed(TEMPLATE.read_text(encoding="utf-8"))
    tree.close()
    assert tree.current is tree.root, "unclosed element in the template"
    return tree


def nodes(tree, level):
    return [n for n in tree.root.walk() if level in n.eli()]


def test_the_surface_is_the_one_lambda_level(template):
    surface = nodes(template, "lambda")
    assert [n.tag for n in surface] == ["main"]


def test_every_clickable_element_opens_an_initiate_zoom_and_every_zoom_is_reachable(template):
    by_id = {n.attrs["id"]: n for n in template.root.walk() if n.attrs.get("id")}
    targets = [n.attrs["data-zoom"] for n in template.root.walk() if n.attrs.get("data-zoom")]
    assert len(targets) >= 3
    for target in targets:
        zoom = by_id[target]
        assert zoom.tag == "dialog" and "initiate" in zoom.eli(), target
    zooms = {n.attrs["id"] for n in nodes(template, "initiate")}
    assert zooms == set(targets)


def test_every_zoom_leads_down_to_architect(template):
    for zoom in nodes(template, "initiate"):
        descents = [n for n in zoom.walk() if "architect" in n.eli()]
        assert descents and all(n.tag == "details" for n in descents), zoom.attrs["id"]


def test_tech_inserts_exist_and_sit_inside_an_architect_descent(template):
    inserts = nodes(template, "tech")
    assert inserts
    for insert in inserts:
        assert insert.tag == "details"
        assert any("architect" in a.eli() for a in insert.ancestors()), insert.attrs.get("id")


def test_ids_are_unique_and_every_internal_link_lands(template):
    ids = [n.attrs["id"] for n in template.root.walk() if n.attrs.get("id")]
    assert len(ids) == len(set(ids)), "docpin anchors notes on ids: they must be unique"
    links = [n.attrs["href"][1:] for n in template.root.walk()
             if n.tag == "a" and (n.attrs.get("href") or "").startswith("#")]
    assert links and set(links) <= set(ids)


def test_the_template_is_self_contained(template):
    for node in template.root.walk():
        for name in ("src", "href"):
            value = node.attrs.get(name) or ""
            assert not re.match(r"(?:https?:)?//", value), f"{node.tag} {name}={value}"


def test_zooms_open_with_show_never_showmodal(template):
    """showModal() puts the zoom in the top layer, above docpin's note bubble."""
    assert re.search(r"\.show\(\)", template.script)
    assert not re.search(r"\.showModal\s*\(", template.script)


def figure_lists() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The closed lists of forms and node kinds, read from render.py of eli:figures."""
    found = {}
    source = (REPO / "skills" / "figures" / "render.py").read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", None) in ("FORMS", "KINDS"):
            found[node.targets[0].id] = ast.literal_eval(node.value)
    return found["FORMS"], found["KINDS"]


def test_the_template_draws_with_the_figure_grammar(template):
    """No diagram drawn by coordinates: every figure is an eli figure, laid out in HTML."""
    forms, kinds = figure_lists()
    every = list(template.root.walk())
    assert not [n for n in every if n.tag == "text"], "SVG <text>: draw it as an eli figure"
    assert not [n for n in every if "arch-svg" in (n.attrs.get("class") or "")]
    figures = [n for n in every if n.tag == "figure"]
    assert len(figures) >= 4 and all(n.attrs.get("data-figure") in forms for n in figures)
    assert all(n.attrs["data-node"] in kinds for n in every if "data-node" in n.attrs)
    surface = nodes(template, "lambda")[0]
    steps = [n for n in surface.walk() if "data-node" in n.attrs]
    assert len(steps) >= 3 and all(n.attrs.get("data-zoom") for n in steps), "each step opens its zoom"


def test_the_template_shows_a_term_and_its_definition(template):
    terms = [n for n in template.root.walk() if "term" in (n.attrs.get("class") or "").split()]
    assert terms and all((n.attrs.get("data-def") or "").strip() and n.attrs.get("tabindex") == "0"
                         for n in terms)
    assert "term.addEventListener(\"click\"" in template.script, "a tap must give the term its focus"


# The zoom of a step, opened with its descent, measured as the reader sees it.
MEASURE_ZOOM = r"""
() => {
  const box = document.querySelector("#z-1 > .box");
  const cs = getComputedStyle(box);
  const content = box.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const lead = document.querySelector("#z-1 > .box > .lead");
  const probe = document.createElement("span");
  probe.style.cssText = "position:absolute;visibility:hidden;width:90ch";
  lead.appendChild(probe);
  const ch90 = probe.getBoundingClientRect().width;
  probe.remove();
  const width = (selector) => document.querySelector(selector).getBoundingClientRect().width;
  return {box: width("#z-1 > .box"), main: width("main"), window: document.documentElement.clientWidth,
          content, ch90, lead: width("#z-1 > .box > .lead"), figure: width("#z-1 > .box > figure"),
          table: width("#a-1 table"), open: document.getElementById("z-1").open};
}
"""


def test_a_zoom_takes_the_width_of_the_page():
    """A zoom covers the page, so it takes the page's width; only its prose is held near 90
    characters a line, and figures and tables take the rest. At phone width nothing changes:
    the zoom fills the window but for its 16 px gutters."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for width in (1400, 1000, 390):
                page = browser.new_page(viewport={"width": width, "height": 900}, reduced_motion="reduce")
                page.goto(TEMPLATE.resolve().as_uri() + "#a-1")
                m = page.evaluate(MEASURE_ZOOM)
                page.close()
                assert m["open"], width
                assert abs(m["box"] - min(m["main"], m["window"] - 32)) <= 1, (width, m)
                assert abs(m["figure"] - m["content"]) <= 1, (width, m)
                if m["content"] > m["ch90"]:            # room for more than 90 characters
                    assert m["lead"] <= m["ch90"] + 1, (width, m)
                    assert m["table"] > m["ch90"] + 1, (width, m)
                else:
                    assert abs(m["lead"] - m["content"]) <= 1, (width, m)
            assert width == 390 and m["content"] < m["ch90"]   # the phone case was reached
        finally:
            browser.close()


def test_the_template_carries_no_eli_exemption():
    first = TEMPLATE.read_text(encoding="utf-8").splitlines()[:5]
    assert not any(re.search(r"eli\s*:\s*(?:d[ée]rogation|exemption)", line, re.IGNORECASE) for line in first)


# -- the output style, the skill and the manifests ----------------------------------------------

def frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n")
    block = text.split("---\n", 2)[1]
    return {key.strip(): value.strip() for key, value in
            (line.split(":", 1) for line in block.splitlines() if ":" in line)}


def test_the_style_is_named_described_and_keeps_coding_instructions():
    fields = frontmatter(STYLE.read_text(encoding="utf-8"))
    assert fields.get("name") == "eli"
    assert fields.get("description")
    assert fields.get("keep-coding-instructions") == "true"


@pytest.mark.parametrize("level", ["ELI5", "ELI-lambda", "ELI-initiate", "ELI-Architect", "ELI-Tech"])
def test_the_style_defines_the_five_levels(level):
    text = STYLE.read_text(encoding="utf-8")
    assert re.search(rf"^\| \**{re.escape(level)}", text, re.MULTILINE), f"no row for {level}"


def test_the_skill_is_the_one_the_style_and_the_hook_name():
    fields = frontmatter(SKILL.read_text(encoding="utf-8"))
    plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))["name"]
    qualified = f"{plugin}:{fields['name']}"
    assert qualified == "eli:documents"
    assert qualified in STYLE.read_text(encoding="utf-8")
    assert qualified in HOOK.read_text(encoding="utf-8")
    assert "template.html" in SKILL.read_text(encoding="utf-8")


def test_the_plugin_declares_the_hook_once_on_the_writing_tools():
    hooks = json.loads(HOOKS.read_text(encoding="utf-8"))["hooks"]
    declared = [(group.get("matcher", ""), hook["command"])
                for group in hooks.get("PostToolUse", []) for hook in group["hooks"]]
    assert len(declared) == 1
    matcher, command = declared[0]
    assert set(matcher.split("|")) >= {"Write", "Edit", "MultiEdit"}
    assert command == '"${CLAUDE_PLUGIN_ROOT}"/hooks/eli-document.py'
    assert HOOK.stat().st_mode & 0o111, "the hook is run directly: it must be executable"
    assert HOOK.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3\n")


def test_the_marketplace_lists_the_plugin_at_the_root():
    plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))
    market = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    assert [(p["name"], p["source"]) for p in market["plugins"]] == [(plugin["name"], "./")]


FIGURES = REPO / "skills" / "figures"
EVALS = sorted(p for p in (REPO / "evals").rglob("*")
               if p.is_file() and "results" not in p.relative_to(REPO / "evals").parts)
SHIPPED = [STYLE, SKILL, TEMPLATE, HOOK, REPO / "README.md", FIGURES / "SKILL.md", FIGURES / "template.html",
           FIGURES / "forms.html", FIGURES / "render.py", *EVALS]


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.relative_to(REPO).as_posix())
def test_what_ships_is_generic(path):
    """The plugin was extracted from one person's setup: no first name, no private path, no
    French left over from the original (the hook still accepts the French exemption word)."""
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"\bAli\b", text)
    assert "~/.claude/skills" not in text and "/home/" not in text
    allowed = {"ée"} if path == HOOK else set()   # the d[ée]rogation pattern
    leftovers = {w for w in re.findall(r"\w*[éèàêçùô]\w*", text, re.IGNORECASE)} - allowed
    assert not leftovers, leftovers


def test_eval_scaffold_copies_are_identical():
    """claude plugin eval refuses a scaffold reached through a link or a path out of its case,
    so every case that selects the eli style carries its own copy of select-eli-style.sh:
    the copies must not drift apart."""
    cases = sorted(p.parent for p in (REPO / "evals").glob("*/case.yaml")
                   if "scaffold_script: select-eli-style.sh" in p.read_text(encoding="utf-8"))
    assert len(cases) >= 3, cases
    copies = {case.name: (case / "select-eli-style.sh").read_bytes() for case in cases}
    first = next(iter(copies.values()))
    assert {name for name, data in copies.items() if data != first} == set()

# -- no "80/20" section: the reply ends on its chain, then the user's actions ---------------------

STYLE_MAX_LINES = 270   # the style is sent with every request
LABELS = ["✅ Result", "👉 Next", "❓ Decide", "⚠️ Watch out", "🔀 Git"]   # the labels of the 0.5.0 section

def test_the_style_carries_no_80_20_section():
    """The 80/20 section (0.5.0) was removed at the user's request: "it is worse since we put it
    in". Neither its heading, nor its template, nor one of its labels may come back."""
    text = STYLE.read_text(encoding="utf-8")
    assert "80/20" not in text
    assert not [label for label in LABELS if label in text]
    assert not re.search(r"^(?:✅|👉|❓|🔀|⚠️)", text, re.MULTILINE)

def test_the_style_names_no_to_do_block():
    """The "TO DO" block, which the 80/20 section replaced, does not come back either."""
    assert "TO DO" not in STYLE.read_text(encoding="utf-8")

def test_the_style_fits_in_its_line_budget():
    count = len(STYLE.read_text(encoding="utf-8").splitlines())
    assert count <= STYLE_MAX_LINES, count

def test_the_readme_names_no_80_20_section():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "80/20" not in readme
    assert "TO DO" not in readme

# -- the order of a reply: its destination first, then the shortest chain to it ------------------

def style_section(title: str) -> str:
    """The text of the "## " section of the style whose heading starts with `title`, up to the
    next "## " heading: a rule quoted in another section is not read."""
    lines = STYLE.read_text(encoding="utf-8").splitlines()
    heads, fence = [], ""
    for i, line in enumerate(lines):   # a heading inside a fenced block (a sample reply) is not one
        mark = re.match(r"`{3,}", line)
        if mark and (not fence or mark.group(0) == fence and line.strip() == fence):
            fence = "" if fence else mark.group(0)
        elif not fence and line.startswith("## "):
            heads.append(i)
    found = [i for i in heads if lines[i][3:].startswith(title)]
    assert len(found) == 1, (title, found)
    end = next((i for i in heads if i > found[0]), len(lines))
    return "\n".join(lines[found[0] + 1:end])

def table_after(text: str, header: str) -> list[list[str]]:
    """The body rows of the table whose header row starts with `header`, cell by cell."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith(header)]
    assert len(starts) == 1, (header, starts)
    rows = []
    for line in lines[starts[0] + 2:]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip().strip("|").split("|")])
    return rows

def bullets(text: str) -> list[str]:
    """The top-level bullets of a text, each with its continuation lines joined."""
    items: list[str] = []
    open_item = False
    for line in text.splitlines():
        if line.startswith("- "):
            items.append(line[2:])
            open_item = True
        elif open_item and line.startswith("  ") and line.strip():
            items[-1] += " " + line.strip()
        else:
            open_item = False
    return items

def one(items: list[str], prefix: str) -> str:
    found = [item for item in items if item.startswith(prefix)]
    assert len(found) == 1, (prefix, found)
    return found[0]

def row(rows: list[list[str]], prefix: str) -> tuple[int, list[str]]:
    found = [(i, r) for i, r in enumerate(rows) if r[0].startswith(prefix)]
    assert len(found) == 1, (prefix, [r[0] for r in rows])
    return found[0]

def test_the_style_opens_on_its_two_axes_the_level_and_the_order():
    """The level says how far down a reply goes, the order how its ideas follow each other: both
    are said before the first section, so that every rule below is read through them."""
    opening = STYLE.read_text(encoding="utf-8").split("\n# ", 1)[1].split("\n## ", 1)[0]
    flat = " ".join(opening.split())
    assert "**The level**" in flat and "**The order**" in flat
    assert "the destination first" in flat and "with no jump" in flat
    assert "A number or a detail never comes before the decision it serves" in flat

def test_a_reply_opens_on_its_destination():
    """A question opens on its decision, a report on its verdict, an explanation on its answer."""
    rows = table_after(style_section("The TL;DR"), "| The reply |")
    question = row(rows, "a question to the user")[1][1]
    assert "level-1 heading in capitals" in question
    heading = re.search(r"`# ([^`]+)`", question)
    assert heading and heading.group(1) == heading.group(1).upper(), question
    report = row(rows, "a report:")[1][1]
    assert "done, not done, or done in part" in report and "what failed exactly" in report
    assert row(rows, "a report that leads to a decision")[1][1].startswith("the decision")
    assert row(rows, "an explanation")[1][1].startswith("the answer to the question asked")

def test_a_question_asks_one_thing_and_says_why_it_needs_the_user():
    section = style_section("The TL;DR")
    paragraphs = [" ".join(p.split()) for p in section.split("\n\n")]
    question = one(paragraphs, "**A question asks one thing**")
    assert "the one that blocks most" in question and "the others wait, unasked, until it is answered" in question
    steps = ["its fork", "only what sets it apart", "numbers after", "why the question matters",
             "the recommendation and what applies without an answer"]
    places = [question.find(step) for step in steps]
    assert -1 not in places and places == sorted(places), dict(zip(steps, places))
    tool = one(bullets(section), "Through a multiple-choice question tool")
    assert "its title" in tool and "before the call" in tool

def test_a_report_keeps_only_what_would_change_what_the_reader_does():
    """The filter of a report sharpens "Show less"; a check not made is a risk, and is said."""
    rule = one(bullets(style_section("Show less")), "**A report sharpens the test")
    assert "would the reader do anything different for knowing it?" in rule
    for consequence in ("means used unasked", "an example worked out as proof", "only if it was asked for or failed",
                        "**not** made is a risk", "leaves a trace", "only if it calls for a decision",
                        "a routine caveat is not", "a subject raised once"):
        assert consequence in rule, consequence

def test_the_fork_of_a_question_is_the_one_drawing_left_in_the_terminal():
    section = style_section("What each level shows")
    rows = table_after(section, "| Situation |")
    place, fork = row(rows, "the options of the question the reply asks")
    assert "the terminal" in fork[1] and "fork" in fork[1] and "code block" in fork[1]
    assert place < row(rows, "the idea needs a fork")[0], "the first row wins: the fork before the page"
    rules = bullets(section)
    never = [i for i, rule in enumerate(rules) if rule.startswith("**Never an ASCII tree")]
    assert len(never) == 1 and never[0] + 1 < len(rules)
    exception = rules[never[0] + 1]
    assert exception.startswith("**One exception, the fork of a question**")
    for word in ("code block", "not bullets", "No box, no frame", "never `↗ ↘`", "Two to four options"):
        assert word in exception, word
    blocks = re.findall(r"^```text\n(.*?)^```$", section, re.MULTILINE | re.DOTALL)
    assert len(blocks) == 1, blocks
    arrows = [line for line in blocks[0].splitlines() if "─▶" in line]
    assert len(arrows) >= 2 and len({line.index("─▶") for line in arrows}) == 1, arrows
    assert {line[line.index("─▶") - 1] for line in arrows} >= {"┌", "└"}, "one direction per option"
    assert not set("↗↘┏┓┗┛╔╗╚╝") & set(blocks[0])

def test_a_choice_made_in_the_users_place_is_flagged_in_the_opening():
    """A question blocks; a choice the work made for the user, which hangs on what only they know,
    does not block but is flagged every time, at the top of the reply, never at its end."""
    flag = one(bullets(style_section("The TL;DR")), "**A choice the work made in the user's place")
    for word in ("only they know", "flagged every time, in the opening**", "right after the decision or the verdict",
                 "one line per choice", "what was chosen in bold", "the other way", "what it hangs on",
                 "does not block"):
        assert word in flag, word

def test_the_commands_keep_their_rules():
    """The rules of a command predate the 80/20 section and outlive it: one command alone in its
    block, the machine named, a rollback outside the block."""
    section = style_section("What the user must do")
    flat = " ".join(section.split())
    assert "comes last" in flat and "each naming the machine it runs on" in flat
    rule = one(bullets(section), "**A command lives alone in its")
    for word in ("```bash", "whole on one line", "two machines, two actions", "writes its number in full",
                 "stay outside the block", '"Rollback, only if …:"'):
        assert word in rule, word

def test_each_sentence_stands_alone_and_no_term_is_translated_word_for_word():
    rules = bullets(style_section("Writing"))
    whole = one(rules, "**Fewer sentences")
    assert "**Every sentence stands alone**" in whole and '"it failed"' in whole and "out loud" in whole
    terms = one(rules, "**Technical words as the code says them")
    assert "never translated word for word" in terms and "everyday words" in terms

def test_how_a_project_is_built_is_read_at_architect_on_a_figure_page():
    rows = table_after(style_section("Which level"), "| Signal in the user's message |")
    place, (signal, level) = row(rows, "how a project or a system is built")
    assert "the user's own project included" in signal and "names a file or a folder" in signal
    assert level.startswith("ELI-Architect") and "figure page" in level
    assert '"how is this function coded" stays ELI-Tech' in level
    assert place < row(rows, "a file, a function")[0], "the first row wins: a file named is no ELI-Tech here"
    page = row(table_after(style_section("What each level shows"), "| Situation |"), "how a project is built")
    for word in ("three levels", "open on ELI-Architect", "#eli-architect", "overview first", "one per flow",
                 "lead sentence", "no sentence cut short"):
        assert word in page[1][1], word

def test_the_self_check_asks_after_each_rule_without_growing():
    section = style_section("Self-check")
    assert len(re.findall(r"^\d+\. ", section, re.MULTILINE)) <= 7   # as many questions as in 0.5.0
    flat = " ".join(section.split())
    for asked in ("open on its destination", "level-1 heading in capitals", "no number before the decision",
                  "A question: one only", "its fork in a code block", "in a report act otherwise",
                  "A check not made", "flagged in the opening", "The actions last", "each sentence standing alone",
                  "word for word",
                  "an architecture"):
        assert asked in flat, asked
