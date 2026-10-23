"""The pieces of the plugin that are not the hook: the template of the
eli:documents skill, the output style and the manifests that ship them.

The template is parsed into a tree (html.parser, no dependency): a regular
expression would count a marker quoted in a comment, which is the mistake the
hook itself is built to avoid.
"""
from __future__ import annotations

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


SHIPPED = [STYLE, SKILL, TEMPLATE, HOOK, REPO / "README.md"]


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.name)
def test_what_ships_is_generic(path):
    """The plugin was extracted from one person's setup: no first name, no private path, no
    French left over from the original (the hook still accepts the French exemption word)."""
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"\bAli\b", text)
    assert "~/.claude/skills" not in text and "/home/" not in text
    allowed = {"ée"} if path == HOOK else set()   # the d[ée]rogation pattern
    leftovers = {w for w in re.findall(r"\w*[éèàêçùô]\w*", text, re.IGNORECASE)} - allowed
    assert not leftovers, leftovers
