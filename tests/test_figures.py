"""The eli:figures skill: its contract read in the files (html.parser, no browser),
then render.py run as a user runs it, a process, on the pages it ships, on a witness
that holds every hard defect once, and on the clean twin of that witness.

Every detector of render.py is proved both ways: the witness makes it speak, and its
twin, which differs only by the values that make the defects, keeps it silent at the
edge (14 px text, 15 nodes, nodes side by side, a strip exactly as wide as the page).
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIGURES = REPO / "skills" / "figures"
SKILL = FIGURES / "SKILL.md"
TEMPLATE = FIGURES / "template.html"
GALLERY = FIGURES / "forms.html"
RENDER = FIGURES / "render.py"
BROKEN = REPO / "tests" / "fixtures" / "figure-broken.html"
PLUGIN = REPO / ".claude-plugin" / "plugin.json"
DOCUMENT = REPO / "skills" / "documents" / "template.html"
PAGES = [TEMPLATE, GALLERY]
SHIPPED_PAGES = [*PAGES, DOCUMENT]     # every page that carries figures
LEVELS = ("lambda", "initiate", "architect")
START, END = "/* eli-figures:start */", "/* eli-figures:end */"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


# -- reading the files -------------------------------------------------------------------------

class Node:
    def __init__(self, tag: str, attrs: dict[str, str | None], parent: Node | None) -> None:
        self.tag, self.attrs, self.parent, self.children, self.text = tag, attrs, parent, [], ""

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def ancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    def all_text(self) -> str:
        return self.text + "".join(child.all_text() for child in self.children)

    def classes(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())


class Tree(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", {}, None)
        self.current = self.root

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
        self.current.text += data


def tree(path: Path) -> Tree:
    parsed = Tree()
    parsed.feed(path.read_text(encoding="utf-8"))
    parsed.close()
    assert parsed.current is parsed.root, f"unclosed element in {path.name}"
    return parsed


def constant(name: str):
    """A constant of render.py, read from its source: no import, no stale bytecode."""
    for node in ast.parse(RENDER.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"render.py defines no {name}")


def skill_section(number: int) -> str:
    text = SKILL.read_text(encoding="utf-8")
    found = re.search(rf"^## {number}\. .*?(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    assert found, f"SKILL.md has no step {number}"
    return found.group(0)


def frontmatter(text: str) -> dict[str, str]:
    assert text.startswith("---\n")
    block = text.split("---\n", 2)[1]
    return {key.strip(): value.strip() for key, value in
            (line.split(":", 1) for line in block.splitlines() if ":" in line)}


def shared_block(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.count(START) == 1 and text.count(END) == 1, path.name
    return text[text.index(START):text.index(END) + len(END)]


# -- the skill -----------------------------------------------------------------------------------

def test_the_skill_is_eli_figures_short_and_points_at_its_files():
    text = SKILL.read_text(encoding="utf-8")
    fields = frontmatter(text)
    plugin = re.search(r'"name"\s*:\s*"([^"]+)"', PLUGIN.read_text(encoding="utf-8")).group(1)
    assert f"{plugin}:{fields['name']}" == "eli:figures"
    assert len(text.splitlines()) <= 200
    for name in ("template.html", "forms.html", "render.py"):
        assert name in text, name


def test_the_description_triggers_on_drawing_requests_in_any_language():
    description = frontmatter(SKILL.read_text(encoding="utf-8"))["description"].lower()
    for word in ("drawing", "diagram", "schema", "infographic", "any language", "dessin", "branches",
                 "loops", "five nodes"):
        assert word in description, word


def test_the_steps_come_in_the_order_of_the_method():
    text = SKILL.read_text(encoding="utf-8")
    steps = re.findall(r"^## (\d)\. (.+)$", text, re.MULTILINE)
    assert [int(n) for n, _ in steps] == list(range(1, 9))
    titles = " | ".join(title.lower() for _, title in steps)
    for word in ("brief", "form", "level", "grammar", "text", "build", "render", "hand"):
        assert word in titles, word


def test_the_level_budgets_are_written_and_match_render():
    section = skill_section(3)
    budgets = dict(re.findall(r"^\| ELI-(\w+) \|.*\| (\d+) \|$", section, re.MULTILINE))
    assert {f"eli-{level.lower()}": int(n) for level, n in budgets.items()} == constant("LEVEL_NODES")
    assert f"**{constant('LABEL_WORDS')} words at most**" in section
    assert max(constant("LEVEL_NODES").values()) == constant("MAX_NODES")


# -- one closed list of forms, one of node kinds, one of tones -----------------------------------

def test_the_forms_are_one_closed_list_in_the_skill_the_gallery_and_render():
    in_skill = re.findall(r"^\|[^|\n]+\| `(\w+)` \|", skill_section(2), re.MULTILINE)
    gallery = tree(GALLERY)
    sections = [n.attrs["id"].removeprefix("form-") for n in gallery.root.walk()
                if n.tag == "section" and (n.attrs.get("id") or "").startswith("form-")]
    assert in_skill == list(constant("FORMS")) == sections
    for section in (n for n in gallery.root.walk() if (n.attrs.get("id") or "").startswith("form-")):
        figures = {f.attrs["data-figure"] for f in section.walk() if f.tag == "figure"}
        assert figures == {section.attrs["id"].removeprefix("form-")}, section.attrs["id"]


def test_the_node_kinds_are_one_closed_list_shown_once_each_in_the_gallery():
    in_skill = re.findall(r"^\| `(\w+)` \|", skill_section(4), re.MULTILINE)
    kinds = list(constant("KINDS"))
    tones = re.findall(r'^\[data-tone="(\w+)"\]', shared_block(TEMPLATE), re.MULTILINE)
    assert in_skill == kinds + tones, "step 4 holds the kinds table, then the tones table"
    gallery = tree(GALLERY)
    strip = next(n for n in gallery.root.walk() if n.attrs.get("id") == "kinds")
    assert sorted(n.attrs["data-node"] for n in strip.walk() if "data-node" in n.attrs) == sorted(kinds)
    assert sorted(n.attrs["data-tone"] for n in strip.walk() if n.tag == "li") == sorted(tones)


@pytest.mark.parametrize("path", SHIPPED_PAGES, ids=lambda p: p.parent.name + "/" + p.name)
def test_every_figure_and_node_of_a_page_is_in_the_lists(path):
    found = tree(path)
    figures = [n for n in found.root.walk() if n.tag == "figure"]
    assert figures and all(n.attrs.get("data-figure") in constant("FORMS") for n in figures)
    nodes = [n for n in found.root.walk() if "data-node" in n.attrs]
    assert nodes and all(n.attrs["data-node"] in constant("KINDS") for n in nodes)


@pytest.mark.parametrize("path", SHIPPED_PAGES, ids=lambda p: p.parent.name + "/" + p.name)
def test_no_svg_text_in_a_figure(path):
    for node in tree(path).root.walk():
        if node.tag == "text":
            assert not any(a.tag == "figure" for a in node.ancestors()), "SVG <text> in a figure"


# -- the page: panels, TL;DR, terms, self-contained, the shared CSS --------------------------------

def test_the_template_has_one_panel_per_level_and_a_selector_for_each():
    found = tree(TEMPLATE)
    panels = [n for n in found.root.walk() if "data-eli" in n.attrs]
    assert [n.attrs["data-eli"] for n in panels] == list(LEVELS)
    assert all(n.attrs.get("id") == f"eli-{n.attrs['data-eli']}" for n in panels)
    assert [n.attrs["id"] for n in panels if "data-open" in n.attrs] == ["eli-lambda"]
    links = [n.attrs["href"] for n in found.root.walk() if n.tag == "a"]
    assert links == [f"#eli-{level}" for level in LEVELS]
    for panel in panels:
        assert any(n.tag == "figure" for n in panel.walk()), panel.attrs["id"]


def test_the_tldr_sits_above_the_selector_in_one_to_three_sentences():
    order = list(tree(TEMPLATE).root.walk())
    tldr = next(i for i, n in enumerate(order) if "data-tldr" in n.attrs)
    selector = next(i for i, n in enumerate(order) if n.tag == "a" and n.attrs["href"].startswith("#eli-"))
    assert tldr < selector
    sentences = re.findall(r"[^.!?]+[.!?]", order[tldr].all_text().replace("TL;DR", ""))
    assert 1 <= len(sentences) <= 3


@pytest.mark.parametrize("path", SHIPPED_PAGES, ids=lambda p: p.parent.name + "/" + p.name)
def test_every_term_carries_its_definition_and_takes_the_focus(path):
    terms = [n for n in tree(path).root.walk() if "term" in n.classes()]
    assert terms
    for term in terms:
        assert (term.attrs.get("data-def") or "").strip(), term.all_text()
        assert term.attrs.get("tabindex") == "0" and "title" not in term.attrs, term.all_text()
    block = shared_block(path)
    assert "content:attr(data-def)" in block
    assert re.search(r"\.term:hover::after,\.term:focus::after\{display:block\}", block)


@pytest.mark.parametrize("path", [*SHIPPED_PAGES, BROKEN], ids=lambda p: p.parent.name + "/" + p.name)
def test_the_pages_are_self_contained(path):
    for node in tree(path).root.walk():
        for name in ("src", "href"):
            value = node.attrs.get(name) or ""
            assert not re.match(r"(?:https?:)?//", value), f"{node.tag} {name}={value}"
        assert not (node.tag == "link" and node.attrs.get("rel") == "stylesheet"), "no outside stylesheet"
    assert "@import" not in path.read_text(encoding="utf-8")


def test_the_shared_css_block_is_the_same_byte_for_byte():
    block = shared_block(TEMPLATE)
    assert block == shared_block(GALLERY)
    assert block == shared_block(DOCUMENT), "the documents template copies it too"
    for token in ("--you", "--sys", "--key", "--ok", "[data-node=", ".f-to", ".term"):
        assert token in block, token


# -- render.py, run as a process ---------------------------------------------------------------------

def render(*pages: Path, out: Path, python: list[str] | None = None, env: dict | None = None):
    done = subprocess.run([*(python or [sys.executable]), str(RENDER), *map(str, pages), "--out", str(out)],
                          capture_output=True, text=True, timeout=600, check=False, env=env)
    return done.returncode, done.stdout, done.stderr


@pytest.fixture(scope="module")
def shipped(tmp_path_factory):
    out = tmp_path_factory.mktemp("shipped")
    return {page.name: (*render(page, out=out), out) for page in PAGES}


@pytest.mark.parametrize("name", [p.name for p in PAGES])
def test_render_finds_no_defect_in_what_ships(shipped, name):
    code, stdout, stderr = shipped[name][:3]
    assert code == 0, stdout + stderr
    assert "no defect" in stdout and "DEFECT" not in stdout


def nodes_by_state(stdout: str, page: str) -> dict[str, int]:
    found = {}
    for state, body in re.findall(rf"^{re.escape(page)} · (\S+)\n((?:  .*\n)+)", stdout, re.MULTILINE):
        row = next(line for line in body.splitlines() if line.strip().startswith("1400 light "))
        found[state] = int(row.split()[6])
    return found


def test_render_shows_one_level_at_a_time_and_captures_every_state(shipped):
    _, stdout, _, out = shipped["template.html"]
    found = tree(TEMPLATE).root
    expected = {}
    for panel in (n for n in found.walk() if "data-eli" in n.attrs):
        expected[panel.attrs["id"]] = sum(1 for n in panel.walk() if "data-node" in n.attrs)
    assert len(set(expected.values())) == len(expected), "the levels must differ to be told apart"
    assert nodes_by_state(stdout, "template.html") == expected
    for state in expected:
        light, dark, phone = (out / f"template-{state}-{v}.png" for v in ("1400-light", "1400-dark", "390-light"))
        assert all(f"png {p}" in stdout for p in (light, dark, phone))
        assert light.read_bytes() != dark.read_bytes(), f"{state}: dark looks like light"
    pictures = {(out / f"template-{s}-1400-light.png").read_bytes() for s in expected}
    assert len(pictures) == len(expected), "two levels rendered the same picture"
    terms = sorted(p.name for p in out.glob("template-*-term.png"))
    assert terms == sorted(f"template-{s}-{v}-light-term.png" for s in ("eli-initiate", "eli-architect")
                           for v in ("1400", "390"))


# Each class of hard defect, and the elements of the witness that must be named for it.
WITNESS = {
    "hscroll": ["div.wide"],
    "text-cut": ["p.clip", "p.off", "div[data-node=action].spill"],
    "overlap": ['div[data-node=action].over "overlap B"'],
    "small-text": ["p.tiny"],
    "too-many-nodes": ["figure#many"],
    "term-hidden": ["span.term"],
    "low-contrast": ["p.pale", "p.ink"],
    "loose-link": ["div.f-to"],
}
# Defects that show in some windows only, and those windows.
ONLY_IN = {"p.ink": "1400 dark"}
CONTRACT = ('unknown form "flowchart"', 'unknown node kind "widget"', "SVG <text> in a figure")


@pytest.fixture(scope="module")
def witness(tmp_path_factory):
    return render(BROKEN, out=tmp_path_factory.mktemp("witness"))


@pytest.mark.parametrize("kind", WITNESS)
def test_render_names_each_defect_of_the_witness(witness, kind):
    code, stdout, _ = witness
    assert code == 1
    lines = [line for line in stdout.splitlines() if line.startswith(f"DEFECT {kind} · figure-broken.html")]
    for element in WITNESS[kind]:
        assert any(element in line for line in lines), f"{kind}: {element} not named\n{stdout}"
    assert len(lines) == len(WITNESS[kind]) * (2 if kind == "term-hidden" else 1), lines
    for element, windows in ONLY_IN.items():
        for line in (line for line in lines if element in line):
            assert line.split(" · ")[3] == windows, f"{element} should show in {windows} only: {line}"


@pytest.mark.parametrize("detail", CONTRACT)
def test_render_names_each_breach_of_the_contract(witness, detail):
    assert any(line.startswith("DEFECT contract") and detail in line for line in witness[1].splitlines())


def test_the_witness_shows_each_defect_in_every_window(witness):
    for line in witness[1].splitlines():
        if line.startswith("DEFECT") and not line.startswith("DEFECT term-hidden") \
                and not any(element in line for element in ONLY_IN):
            assert "1400 light, 1400 dark, 390 light" in line, line


TWIN = {
    BROKEN.read_text(encoding="utf-8").split('<style id="defects">')[1].split("</style>")[0]:
        "\n.wide{width:100%}\n.clip{width:120px;overflow:hidden;white-space:normal}\n.off{margin-left:0}\n"
        ".spill{white-space:normal}\n.over{margin-left:0}\n"
        ".tiny{font-size:14px}\n.extra{display:none}\n.pale{color:#737373}\n.loose{margin-left:0}\n"
        "@media (prefers-color-scheme: dark){.ink{background:#fbfaf7}}\n",
    'data-figure="flowchart"': 'data-figure="chain"',
    'data-node="widget"': 'data-node="action"',
    '<text x="0" y="18" font-size="16">svg text</text>': '<rect width="20" height="20"/>',
}


def test_the_clean_twin_of_the_witness_has_no_defect(tmp_path):
    text = BROKEN.read_text(encoding="utf-8")
    for old, new in TWIN.items():
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    twin = tmp_path / "figure-twin.html"
    twin.write_text(text, encoding="utf-8")
    code, stdout, stderr = render(twin, out=tmp_path / "out")
    assert code == 0, stdout + stderr
    # the edge is reached: 14 px is the smallest text, the full figure holds 15 nodes, the grey
    # is at 4.54:1 (its witness at 4.48:1), and the arrow ends sit 8 px from their nodes
    table = stdout.split("figure-twin.html · page\n")[1]
    assert re.search(r"^  1400 light\s+0\s+0\s+0\s+14\s+21\s", table, re.MULTILINE), table


@pytest.fixture(scope="module")
def document(tmp_path_factory):
    out = tmp_path_factory.mktemp("document")
    return (*render(DOCUMENT, out=out), out)


def test_the_documents_template_renders_clean_and_its_surface_fits_one_screen(document):
    code, stdout, stderr, _ = document
    assert code == 0, stdout + stderr
    assert "no defect" in stdout
    rows = re.search(r"^template\.html · surface\n  viewport.*\n((?:  .*\n)+)", stdout, re.MULTILINE).group(1)
    light = next(line.split() for line in rows.splitlines() if line.strip().startswith("1400 light "))
    words, height, window = int(light[7]), int(light[8]), light[9]
    assert window == "1400x900" and height <= 900, f"the surface is {height} px high: one screen at most"
    assert words <= 300


def test_render_measures_a_zoom_alone_with_its_descents_open(document):
    code, stdout, _, tmp_path = document
    assert code == 0
    zooms = [n.attrs["id"] for n in tree(DOCUMENT).root.walk()
             if n.tag == "dialog" and "zoom" in n.classes()]
    states = re.findall(r"^template\.html · (\S+)$", stdout, re.MULTILINE)
    assert states == ["surface", *zooms]
    surface = {line.split(" · ")[4] for line in stdout.splitlines() if line.startswith("DEFECT") and " · surface · " in line}
    for line in stdout.splitlines():
        if line.startswith("DEFECT") and " · surface · " not in line:
            assert line.split(" · ")[4] not in surface, f"a zoom measured the surface behind it: {line}"
    # the descent and its ELI-Tech insert are open: the window grew to show the whole zoom,
    # and the picture is that window
    width, height = map(int, re.search(r"^template\.html · z-1\n  viewport.*\n  1400 light .* (\d+)x(\d+)$",
                                       stdout, re.MULTILINE).groups())
    assert (width, height > 900) == (1400, True)
    png = (tmp_path / "template-z-1-1400-light.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and int.from_bytes(png[20:24], "big") == height


def test_render_exits_3_without_playwright(tmp_path):
    code, _, stderr = render(TEMPLATE, out=tmp_path, python=[sys.executable, "-S"])
    assert code == 3 and "Playwright is missing" in stderr and "uv sync" in stderr


def test_render_exits_3_without_chromium(tmp_path):
    env = {**__import__("os").environ, "PLAYWRIGHT_BROWSERS_PATH": str(tmp_path / "no-browsers")}
    code, _, stderr = render(TEMPLATE, out=tmp_path, env=env)
    assert code == 3 and "playwright install chromium" in stderr


def test_render_exits_3_on_a_page_that_does_not_exist(tmp_path):
    code, _, stderr = render(tmp_path / "nowhere.html", out=tmp_path)
    assert code == 3 and "no such page" in stderr
