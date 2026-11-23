# eli

**Claude explains top-down, one level at a time. Plain words and a diagram first, then the
technical detail when you ask for it, in one word.**

![The ELI levels: ELI-lambda by default, then ELI-initiate, ELI-Architect and ELI-Tech, each one a step further down](docs/figures/levels.svg)

Subjects are often big and tangled. Diving into all the technical detail at once makes them hard
to get into, so eli gives Claude and you a shared vocabulary of named levels (ELI is short for
*Explain Like I'm…*):

| Level | Explain like I'm… | What you get |
|---|---|---|
| ELI5 | a curious child | one everyday image |
| **ELI-lambda**, the default | anyone of normal intelligence, new to the subject | what it does for you, and a diagram |
| ELI-initiate | interested and willing to learn | the mechanisms that make the idea possible and convenient |
| ELI-Architect | the person who designs the solution | components, flows, trade-offs, the numbers that constrain |
| ELI-Tech | the person who implements it | files, functions, commands, code |

- **Claude guesses the level** from your message: a new subject starts at ELI-lambda, a question
  about a file goes to ELI-Tech, a proposed design goes to ELI-Architect, "go deeper" goes one
  notch down. The level is sticky: it follows the subject, not each message.
- **You can always name one**: "ELI-archi: how would the cache work?"
- **Every explaining reply ends with a level line** that says which level it chose and what one
  notch down would hold, so a wrong guess is corrected in one word.
- **ELI-lambda means a diagram** whenever a new idea comes in: a picture is how a new idea gets
  into a brain. A plain factual answer stays one line.
- **A drawing is a page, not ASCII art**: ask for a diagram, or let an idea fork, loop or pass
  between several actors, and Claude draws it on an HTML page at two or three levels, where a
  shape says what sort of thing a node is and a colour says who acts. The terminal keeps a
  straight line of arrows or a table.
- **Every word explains itself**: an abbreviation or an uncommon word is explained where it
  first appears; in a page, its definition shows when you hover or tap it.
- **Documents follow the same model**: a one-screen surface in plain words whose every element
  opens, on click, a zoom with the mechanisms; each zoom has an "Under the hood" section at the
  ELI-Architect level, with ELI-Tech inserts where a precise point needs one.

## What you get

| Piece | What it does |
|---|---|
| the **eli** output style | the levels, how to pick one, a TL;DR that stands on its own (each decision with its problem, its recommendation and what applies without an answer), technical words kept as the code spells them, the forms (diagram before prose, tables for comparisons), the level line, and a "TO DO" block that ends a reply with what is left to do |
| the **`eli:documents`** skill | how a document carries the levels, with a ready template: a one-screen surface, zooms as wide as the page, light and dark, phone width, keyboard, links that open a precise level (`#a-2`) |
| the **`eli:figures`** skill | how to draw: what to show or hide at each level, five forms (chain, branch, cycle, lanes, map), six shapes and five colours that are their own legend, a template, a gallery, and `render.py`, which captures every level and measures what a reader would trip on |
| the **eli-document** check | sends the session back to a document it just wrote when it is Markdown or has no visual, and warns when it lacks its levels or its TL;DR, loads from the network, has a surface over 300 words, uses an abbreviation it never explains, or holds too much prose per picture |

It pairs well with [docpin](https://github.com/elphono/docpin), which lets you pin notes on the
documents a session writes and sends them back to it. The template is built to work under
docpin's notes. Neither needs the other. eli replaces docpin's optional **visual-first** plugin,
style and check alike: if you had it, disable it (`/plugin disable visual-first@docpin`), or every
document is checked twice.

## Install

1. In a Claude Code session, type:

   ```text
   /plugin install eli --marketplace elphono/eli
   ```

2. Pick **eli:eli** in `/output-style`.
3. **Start a new session**: an output style is read when a session starts.

To try it, ask *"how does HTTPS keep my password secret?"*, then *"go deeper"*, then
*"ELI-tech"*.

## Before you start

- **Claude Code** 2.1.275 or later.
- **Python 3.12 or newer**, available as `python3`, for the document check. It installs no
  package.
- To render and measure figures (`render.py` of `eli:figures`):
  [uv](https://docs.astral.sh/uv/), which installs Playwright 1.58 for that script alone from
  any folder (`uv run .../skills/figures/render.py PAGE --out DIR`), and Chromium, installed once
  by `uvx playwright@1.58.0 install chromium`. Where Playwright 1.58 is already installed,
  `python3` runs the script too. When something is missing, the script says how to install it.

## How a document is checked

The check runs after each `Write` or `Edit` of a page that counts as a document: one under a
`docs/` folder of the project, or, when docpin is installed, whatever docpin tracks. READMEs,
`CLAUDE.md`, working notes (`plans/`, `drafts/`) and figure sources (`figures/`) are never
checked.

| The document | Verdict |
|---|---|
| Markdown, or an HTML page with no visual (`svg`, `img`, `canvas`, `table`, an eli figure with `data-figure`) | **blocked**: the session reworks it before moving on |
| no ELI-lambda surface or no ELI-initiate zoom (`data-eli` attributes, never the text) | warning |
| no TL;DR (a `data-tldr` attribute) | warning |
| loads a script, a stylesheet or an image from the network | warning |
| a surface over 300 words (the text shown in `data-eli="lambda"`) | warning, with the count |
| an abbreviation (`HUD`, `MIDI`) that no `data-def` or `abbr title` explains anywhere in the page; code, common ones (OK, PDF, URL, USB) and words in capitals for emphasis are left alone | warning, listing them |
| more than 4 paragraphs per visual, or a new image over 1 MB | warning |

`touch ~/.claude/eli-off` turns the check off on a machine. A page whose form is justified, such
as a transcript, opts out with this in its first five lines:

```html
<!-- eli: exemption — a raw transcript -->
```

## Develop

```text
uv sync
uv run playwright install chromium
uv run pytest -q
uv run ruff check hooks tests tools skills
claude plugin validate --json . > report.json; python3 tools/check_plugin_report.py report.json
```

Chromium is for the tests of `render.py` and of the template's zooms; the plugin itself needs
neither.

## License

MIT
