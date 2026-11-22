#!/usr/bin/env python3
"""Render an eli figure page (or an eli document) to PNG, and measure what a reader
would trip on.

    python3 render.py PAGE [PAGE ...] --out DIR

What is captured, state by state:

| The page                              | Its states                                          |
|---------------------------------------|-----------------------------------------------------|
| level panels (`[data-eli][id^=eli-]`) | each panel, by its `#eli-<level>` hash              |
| zooms (`dialog.zoom`)                 | the surface, then each zoom by its hash, descents open |
| anything else                         | the page                                            |

Each state is captured at 1400x900 light, 1400x900 dark and 390x844 light, whole
page; then, when it holds a term, with the definition of its first term shown: by
hovering it at 1400, by tapping it at 390 (file names ending in `-term.png`).

One line per PNG, then a table of measures per state, then one line per defect.
Defects, all hard:

| Defect          | What it is                                                          |
|-----------------|---------------------------------------------------------------------|
| hscroll         | the page scrolls sideways                                           |
| text-cut        | text outside the window, cut by a clipping box, or out of its node   |
| overlap         | two nodes overlap                                                   |
| small-text      | text displayed under MIN_TEXT_PX                                    |
| too-many-nodes  | more than MAX_NODES nodes shown in one figure                       |
| contract        | a form or node kind outside the closed lists, or SVG <text> in a figure |
| term-hidden     | a term whose definition does not show on hover or tap              |

Exit codes: 0 no defect, 1 defects, 3 cannot render (Playwright or Chromium missing,
a page that does not exist or does not load). Playwright is a development
dependency of the eli plugin, never a runtime one.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

FORMS = ("chain", "branch", "cycle", "lanes", "map")
KINDS = ("actor", "action", "question", "store", "result", "note")
MIN_TEXT_PX = 14
MAX_NODES = 15
# Budgets of the skill, noted but not defects: nodes shown per level, words per node label.
LEVEL_NODES = {"eli-lambda": 9, "eli-initiate": 12, "eli-architect": 15}
LABEL_WORDS = 8
VIEWPORTS = (("1400", 1400, 900, "light"), ("1400", 1400, 900, "dark"), ("390", 390, 844, "light"))
SETTLE_MS = 350

MISSING_PLAYWRIGHT = ("render.py: Playwright is missing. In the eli repository: `uv sync` (it is a dev "
                      "dependency), then `uv run playwright install chromium`; elsewhere: "
                      "`pip install playwright==1.58.0 && python3 -m playwright install chromium`.")
MISSING_CHROMIUM = ("render.py: Chromium for Playwright cannot start ({error}). Install it: "
                    "`uv run playwright install chromium` (or `python3 -m playwright install chromium`).")

# Runs in the page. Returns the measures of the state as it is displayed, and its defects.
MEASURE = r"""
([forms, kinds, minPx, maxNodes, labelWords, scope]) => {
  const vw = document.documentElement.clientWidth;
  // A zoom covers the page: only what it shows is measured.
  const root = (scope && document.getElementById(scope)) || document.body;
  const shown = (el) => el.checkVisibility({opacityProperty: true, visibilityProperty: true,
                                            checkOpacity: true, checkVisibilityCSS: true});
  const name = (el) => {
    let s = el.tagName.toLowerCase();
    if (el.id) s += "#" + el.id;
    for (const a of ["data-figure", "data-node", "data-tone"]) {
      if (el.hasAttribute(a)) s += `[${a}=${el.getAttribute(a)}]`;
    }
    if (!el.id && typeof el.className === "string" && el.className.trim()) {
      s += "." + el.className.trim().split(/\s+/).join(".");
    }
    const t = (el.textContent || "").trim().replace(/\s+/g, " ");
    if (t) s += ` "${t.length > 48 ? t.slice(0, 47) + "…" : t}"`;
    return s;
  };
  const defects = [];
  const add = (kind, el, detail) => defects.push({kind, element: name(el), detail});

  // Sideways scrolling, and what sticks out
  const doc = document.documentElement;
  const hscroll = Math.max(0, doc.scrollWidth - doc.clientWidth, document.body.scrollWidth - doc.clientWidth);
  if (hscroll > 1) {
    const out = [...document.body.querySelectorAll("*")].filter(
      (el) => shown(el) && el.getBoundingClientRect().right > vw + 1 &&
              ![...el.children].some((c) => c.getBoundingClientRect().right > vw + 1));
    const tips = [...document.querySelectorAll(".term")].filter((el) => getComputedStyle(el, "::after").display !== "none");
    const culprit = out[0] || (tips[0] && tips[0]) || document.body;
    add("hscroll", culprit, `${Math.round(hscroll)} px wider than the window` + (!out[0] && tips[0] ? " (its definition)" : ""));
  }

  // Text: size, words, and whether each line is whole and inside its box
  let minFont = Infinity, minAt = "", words = 0;
  const cut = new Set();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let t = walker.nextNode(); t; t = walker.nextNode()) {
    if (!t.data.trim()) continue;
    const el = t.parentElement;
    if (!el || el.closest("script,style,noscript,template,title") || !shown(el)) continue;
    const range = document.createRange();
    range.selectNodeContents(t);
    const rects = [...range.getClientRects()].filter((r) => r.width > 0.5 && r.height > 0.5);
    if (!rects.length) continue;
    words += t.data.trim().split(/\s+/).length;
    let size = parseFloat(getComputedStyle(el).fontSize);
    if (el instanceof SVGElement && el.getScreenCTM && el.getScreenCTM()) {
      const m = el.getScreenCTM();
      size *= Math.hypot(m.a, m.b);
    }
    if (size < minFont) { minFont = size; minAt = name(el); }
    if (size < minPx - 0.01) add("small-text", el, `${size.toFixed(1)} px, under ${minPx} px`);
    // Text in a box that scrolls (code in a <pre>) is reached by scrolling it, not cut.
    let scrolls = false;
    for (let a = el; a && a !== root.parentElement; a = a.parentElement) {
      if (/auto|scroll/.test(getComputedStyle(a).overflowX) && a.scrollWidth > a.clientWidth) { scrolls = true; break; }
    }
    for (const r of rects) {
      if (scrolls) break;
      if (r.right > vw + 1 || r.left < -1) {
        if (!cut.has(el)) { cut.add(el); add("text-cut", el, "outside the window"); }
        break;
      }
      for (let a = el; a && a !== document.body; a = a.parentElement) {
        const cs = getComputedStyle(a);
        const clips = /hidden|clip/.test(cs.overflowX + " " + cs.overflowY);
        const node = a.hasAttribute("data-node");
        if (!clips && !node) continue;
        const b = a.getBoundingClientRect();
        const tol = 1;
        if (r.left < b.left - tol || r.right > b.right + tol || r.top < b.top - tol || r.bottom > b.bottom + tol) {
          if (!cut.has(el)) {
            cut.add(el);
            add("text-cut", el, node ? `out of its node ${name(a)}` : `cut by ${name(a)}`);
          }
          break;
        }
      }
    }
  }

  // Nodes: how many in each figure, and none on top of another
  const nodes = [...root.querySelectorAll("[data-node]")].filter(shown);
  let overlaps = 0;
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i].getBoundingClientRect();
    for (let j = i + 1; j < nodes.length; j++) {
      if (nodes[i].contains(nodes[j]) || nodes[j].contains(nodes[i])) continue;
      const b = nodes[j].getBoundingClientRect();
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (w > 1 && h > 1) {
        overlaps++;
        add("overlap", nodes[i], `overlaps ${name(nodes[j])} by ${Math.round(w)}x${Math.round(h)} px`);
      }
    }
  }
  for (const fig of root.querySelectorAll("figure[data-figure]")) {
    if (!shown(fig)) continue;
    const form = fig.getAttribute("data-figure");
    if (!forms.includes(form)) add("contract", fig, `unknown form "${form}", not one of ${forms.join(", ")}`);
    const count = [...fig.querySelectorAll("[data-node]")].filter(shown).length;
    if (count > maxNodes) add("too-many-nodes", fig, `${count} nodes, over ${maxNodes}`);
    for (const text of fig.querySelectorAll("svg text")) add("contract", text, "SVG <text> in a figure");
  }
  for (const node of nodes) {
    const kind = node.getAttribute("data-node");
    if (!kinds.includes(kind)) add("contract", node, `unknown node kind "${kind}", not one of ${kinds.join(", ")}`);
  }
  const longLabels = [...root.querySelectorAll("figure[data-figure] [data-node] .f-t")].filter(shown)
    .map((el) => (el.textContent || "").trim().replace(/\s+/g, " "))
    .filter((text) => text.split(" ").length > labelWords);
  return {defects, longLabels, hscroll: Math.round(hscroll), cut: cut.size, overlaps,
          minFont: minFont === Infinity ? null : Math.round(minFont * 10) / 10, minAt,
          nodes: nodes.length, words, height: doc.scrollHeight, window: `${innerWidth}x${innerHeight}`};
}
"""

STATES = r"""
() => {
  const panels = [...document.querySelectorAll('[data-eli][id^="eli-"]')]
    .map((p) => p.id).filter((id) => /^eli-(lambda|initiate|architect)$/.test(id));
  const zooms = [...document.querySelectorAll("dialog.zoom[id]")].map((d) => d.id);
  return {panels, zooms};
}
"""

OPEN_ZOOM = r"""
(id) => {
  const dlg = document.getElementById(id);
  if (!dlg) return 0;
  dlg.querySelectorAll("details").forEach((d) => { d.open = true; });
  const box = dlg.querySelector(".box") || dlg;
  return Math.ceil(box.scrollHeight);
}
"""

PICK_TERM = r"""
(scope) => {
  const root = (scope && document.getElementById(scope)) || document;
  const term = [...root.querySelectorAll(".term")].find((t) =>
    t.checkVisibility({opacityProperty: true, visibilityProperty: true}) && t.getBoundingClientRect().width > 0);
  if (!term) return false;
  term.setAttribute("data-render-term", "");
  term.scrollIntoView({block: "center"});
  return true;
}
"""

TERM_SHOWN = r"""
() => {
  const term = document.querySelector("[data-render-term]");
  const tip = getComputedStyle(term, "::after");
  return {shown: tip.display !== "none" && tip.visibility !== "hidden" && tip.content !== "none" &&
                 tip.content !== "normal" && parseFloat(tip.opacity) > 0,
          def: term.getAttribute("data-def") || ""};
}
"""


class CannotRender(Exception):
    """The page cannot be rendered at all: exit code 3."""


def states_of(page) -> list[tuple[str, str]]:
    found = page.evaluate(STATES)
    if found["panels"]:
        return [(p, "#" + p) for p in found["panels"]]
    if found["zooms"]:
        return [("surface", "")] + [(z, "#" + z) for z in found["zooms"]]
    return [("page", "")]


def settle(page) -> None:
    page.evaluate("document.fonts.ready.then(() => true)")
    page.wait_for_timeout(SETTLE_MS)


def load(context, url: str):
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(url, wait_until="load")
    except Exception as error:  # any failure to load means: cannot render
        page.close()
        raise CannotRender(f"{url}: {error}") from error
    settle(page)
    return page, errors


def measure(page, scope: str | None = None) -> dict:
    return page.evaluate(MEASURE, [list(FORMS), list(KINDS), MIN_TEXT_PX, MAX_NODES, LABEL_WORDS, scope])


def fit_zoom(page, state: str, width: int, height: int) -> None:
    """A zoom scrolls inside its own box: grow the window until the whole box shows."""
    needed = page.evaluate(OPEN_ZOOM, state)
    if needed + 64 > height:
        page.set_viewport_size({"width": width, "height": needed + 64})
    settle(page)


def render_page(browser, path: Path, out: Path, report: list[str], defects: list[tuple]) -> None:
    url = path.resolve().as_uri()
    stem = path.stem
    probe = browser.new_context(viewport={"width": 1400, "height": 900})
    page, _ = load(probe, url)
    states = states_of(page)
    probe.close()
    contexts = {}
    for label, width, height, scheme in VIEWPORTS:
        contexts[(label, scheme)] = browser.new_context(
            viewport={"width": width, "height": height}, color_scheme=scheme, reduced_motion="reduce",
            device_scale_factor=1, has_touch=width < 600, is_mobile=False)
    for state, fragment in states:
        zoom = bool(fragment) and not state.startswith("eli-")
        rows = []
        for label, width, height, scheme in VIEWPORTS:
            page, errors = load(contexts[(label, scheme)], url + fragment)
            if zoom:
                fit_zoom(page, state, width, height)
            shot = out / f"{stem}-{state}-{label}-{scheme}.png"
            page.screenshot(path=str(shot), full_page=True)
            report.append(f"png {shot}")
            rows.append((f"{label} {scheme}", measure(page, state if zoom else None)))
            for error in errors:
                report.append(f"note: {path.name} {state}: script error: {error}")
            page.close()
        for label, width, height, scheme, how in (("1400", 1400, 900, "light", "hover"),
                                                  ("390", 390, 844, "light", "tap")):
            page, _ = load(contexts[(label, scheme)], url + fragment)
            if zoom:
                fit_zoom(page, state, width, height)
            if not page.evaluate(PICK_TERM, state if zoom else None):
                page.close()
                break
            term = page.locator("[data-render-term]")
            if how == "tap":
                term.tap()
            else:
                term.hover()
            page.wait_for_timeout(150)
            shown = page.evaluate(TERM_SHOWN)
            shot = out / f"{stem}-{state}-{label}-{scheme}-term.png"
            page.screenshot(path=str(shot), full_page=True)
            report.append(f"png {shot}")
            measured = measure(page, state if zoom else None)
            if not shown["shown"]:
                measured["defects"].append({"kind": "term-hidden", "element": f'span.term "{shown["def"][:40]}"',
                                            "detail": f"its definition does not show on {how}"})
            rows.append((f"{label} {scheme} term ({how})", measured))
            page.close()
        report.append(table(path.name, state, rows))
        first = rows[0][1]
        budget = LEVEL_NODES.get(state)
        if budget is not None and first["nodes"] > budget:
            report.append(f"note: {path.name} {state}: {first['nodes']} nodes, over the budget of {budget}")
        for label in first["longLabels"]:
            report.append(f"note: {path.name} {state}: a label over {LABEL_WORDS} words: \"{label}\"")
        for viewport, measured in rows:
            for found in measured["defects"]:
                defects.append((path.name, state, viewport, found["kind"], found["element"], found["detail"]))
    for context in contexts.values():
        context.close()


def table(name: str, state: str, rows: list[tuple[str, dict]]) -> str:
    head = ("viewport", "hscroll px", "text cut", "overlaps", "min text px", "nodes", "words", "height px",
            "window")
    lines = [head] + [(viewport, str(m["hscroll"]), str(m["cut"]), str(m["overlaps"]),
                       "-" if m["minFont"] is None else f'{m["minFont"]:g}', str(m["nodes"]),
                       str(m["words"]), str(m["height"]), m["window"]) for viewport, m in rows]
    widths = [max(len(line[i]) for line in lines) for i in range(len(head))]
    body = ["  " + "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(line)).rstrip() for line in lines]
    return "\n".join([f"{name} · {state}", *body])


def grouped(defects: list[tuple]) -> list[str]:
    """One line per defect, the windows where it shows put together."""
    merged: dict[tuple, list[str]] = {}
    for page, state, viewport, kind, element, detail in defects:
        merged.setdefault((page, state, kind, element, detail), []).append(viewport)
    return [f"DEFECT {kind} · {page} · {state} · {', '.join(dict.fromkeys(viewports))} · {element} · {detail}"
            for (page, state, kind, element, detail), viewports in merged.items()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render eli figure pages to PNG and measure them.")
    parser.add_argument("pages", nargs="+", type=Path, help="HTML pages to render")
    parser.add_argument("--out", required=True, type=Path, help="folder for the PNG files")
    args = parser.parse_args(argv)
    missing = [str(p) for p in args.pages if not p.is_file()]
    if missing:
        print(f"render.py: no such page: {', '.join(missing)}", file=sys.stderr)
        return 3
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(MISSING_PLAYWRIGHT, file=sys.stderr)
        return 3
    args.out.mkdir(parents=True, exist_ok=True)
    report: list[str] = []
    defects: list[tuple] = []
    try:
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch()
            except PlaywrightError as error:
                print(MISSING_CHROMIUM.format(error=str(error).splitlines()[0]), file=sys.stderr)
                return 3
            for path in args.pages:
                render_page(browser, path, args.out, report, defects)
            browser.close()
    except CannotRender as error:
        print("\n".join(report))
        print(f"render.py: cannot render {error}", file=sys.stderr)
        return 3
    print("\n".join(report))
    lines = grouped(defects)
    print("\n".join(lines) if lines else "no defect")
    pngs = sum(1 for line in report if line.startswith("png "))
    print(f"render.py: {pngs} PNG, {len(lines)} defect(s)")
    return 1 if lines else 0


if __name__ == "__main__":
    sys.exit(main())

