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

# -- the 80/20 section that ends every reply ------------------------------------------------------

STYLE_MAX_LINES = 270   # the style is sent with every request
LABELS = ["✅ Result:", "👉 Next:", "❓ Decide:", "⚠️ Watch out:", "🔀 Git:"]

def section_template() -> list[str]:
    """The lines of the template of the 80/20 section, cut out of the style: the first
    ````markdown fence under its heading, up to the fence that closes it. A label quoted
    anywhere else in the style is not read."""
    lines = STYLE.read_text(encoding="utf-8").splitlines()
    heading = [i for i, line in enumerate(lines) if line.startswith("## ") and '"80/20"' in line]
    assert len(heading) == 1, heading
    start = next(i for i in range(heading[0], len(lines)) if lines[i] == "````markdown")
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "````")
    return lines[start + 1:end]

def test_the_80_20_template_opens_with_a_rule_then_its_heading():
    filled = [line for line in section_template() if line.strip()]
    assert filled[:2] == ["---", "## 80/20"], filled[:2]

def test_the_80_20_template_carries_the_five_labels_in_order():
    found = [label for line in section_template() for label in LABELS if line.startswith(label)]
    assert found == LABELS, found

def test_the_style_names_no_to_do_block():
    """The 80/20 section replaced the "TO DO" block: two endings would compete."""
    assert "TO DO" not in STYLE.read_text(encoding="utf-8")

def test_the_style_fits_in_its_line_budget():
    count = len(STYLE.read_text(encoding="utf-8").splitlines())
    assert count <= STYLE_MAX_LINES, count

def test_the_readme_names_the_80_20_section():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "80/20" in readme
    assert "TO DO" not in readme
