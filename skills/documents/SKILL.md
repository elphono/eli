---
name: documents
description: Give a document that explains or reports (spec, design note, report, comparison, procedure, review) the ELI form — an ELI-lambda surface whose every element opens on click into an ELI-initiate zoom, each zoom leading down to ELI-Architect, with occasional ELI-Tech inserts. Use it for every HTML document meant for a human reader, starting from the template next to this file.
---

# ELI documents

The levels, the inference table and the forms live in the `eli` output style; the figures, in
the `eli:figures` skill. This skill says how a **document** carries them. If docpin is
installed, its `docpin:annotatable-documents` skill gives the mechanics — where to write the
document, how to hand over the link, how to wait for and answer notes: follow both.

## The model

| Floor | Level | Holds | Does not hold | Reached by |
|---|---|---|---|---|
| surface | ELI-lambda | the promise title; one "who does what" sentence; the TL;DR; one figure of 3 to 5 steps, each a title and a sentence with no jargon; what is done | mechanism, component name, technical number | the page |
| zoom | ELI-initiate | the mechanism, drawn; what works, what not yet; each new word defined | format, protocol, file name | a click on an element |
| descent | ELI-Architect | the components and their flows (a figure); the number that constrains; options and trade-off (a table) | code, function names | "Under the hood", at the bottom of **every** zoom |
| insert | ELI-Tech | path, signature, command, short excerpt; the edge case | a lecture | ⚙, only where a precise point calls for it |

ELI5 has no floor in a document.

## The surface fits one screen

**900 px high at most at 1400x900, and 300 words at most** — the check counts the words of the
`data-eli="lambda"` element and warns above 300. What does not fit goes down into a zoom.
Everything shown passes the style's test, *would the reader miss it?*:

- the way to open the levels takes one line, never a legend of the levels;
- a state mark ("in progress") only on the element whose state differs from the rest;
- a level is named once, quietly, at the end of the summary that opens it; no badge elsewhere.

## Start from the template

Copy `template.html`, which sits in this skill's directory, to the document's place — for
instance `docs/<yyyy-mm-dd>-<subject>.html` — then replace **every** sample text. The template
is light and dark, reads at phone width and opens from the keyboard; it is resized without
being rewritten:

| To | Do |
|---|---|
| have fewer steps | remove the node, its `.f-to` arrow and its `<dialog>` |
| a subject that is not a loop | set `data-figure="chain"`, remove the `.f-cycle` wrapper, its `.f-back` and the `z-loop` zoom |
| nothing done to show | remove `.proof` and the `z-done` zoom |
| another figure in a zoom (a fork, a hand-off, a structure) | take its markup from `forms.html` of the `eli:figures` skill |
| one more ELI-Tech insert | copy a `details.tech` into the descent that needs it, with a new `id` |

Write the page in the reader's language: set `<html lang>` and translate the template's labels
("Click a step for its detail", "Under the hood", "Close", "Done this week") with the samples.

## The convention, attribute by attribute

| Element | Carries | Role |
|---|---|---|
| the surface's `<main>` | `data-eli="lambda"` | the entry level |
| each clickable element | `data-zoom="z-…"`, `role="button"`, `tabindex="0"` | opens the zoom with the same `id` |
| each `<dialog class="zoom">` | `data-eli="initiate"`, `id="z-…"`, `data-tone` of the step | one notch of detail |
| a `<details class="descent">` in **every** zoom | `data-eli="architect"`, `id="a-…"` | "Under the hood" |
| a `<details class="tech">`, inside a descent | `data-eli="tech"`, `id="t-…"` | one precise point of code |
| a figure | `data-figure`, its nodes `data-node` and `data-tone` | the `eli:figures` grammar |
| a term | `class="term" tabindex="0" data-def="…"` | its definition on hover, focus or tap |
| a link to a level | `<a href="#t-…">` (or `#z-…`, `#a-…`) | opens the zoom and the descents that lead to the target |

`id`s are unique. A link ending in `#a-2` opens the descent of zoom 2 directly: that is what to
give in the terminal to point at a precise level. docpin anchors a note on the first `id` it
meets going up, which keeps the note in place when the document changes. A zoom takes the width
of the page it covers; only its prose is held near 90 characters a line.

## The TL;DR, and the decisions

The surface opens on a **TL;DR** (`data-tldr`): one to three whole sentences that are enough by
themselves, written last, once the rest is known. Whoever stops there knows what the document
found and what is expected of them. A document that asks for decisions says, in the TL;DR, how
many there are and what applies without an answer; each one is then stated in a table that also
reads on its own:

| Column | Holds |
|---|---|
| the choice, and the problem it settles | a numbered title, then the problem in whole sentences: what goes wrong today, when, for whom |
| recommended | the option, in a sentence a newcomer understands |
| other choice | the alternative, and what it costs |
| what is checked | how the outcome will show, for each option |

Under the table, one bold sentence says what applies without an answer — usually the
recommendation. The options' technical spelling (flags, file names) goes down a level, into
the descent, never in the table the decision is read from.

## What calls for a picture

In a document, an idea is **drawn first**; prose keeps only what does not draw — a trade-off, a
doubt, a nuance. The test is not length but the presence of something to understand:

| The passage carries | Example | Form |
|---|---|---|
| a concept, a notion of the project | what a "lease" or a "recipe" is | a figure: `map` |
| a mechanism | what happens when the resource is already taken | a figure: `chain` or `branch` |
| a flow between several actors | who writes what, in which order, where | a figure: `lanes` |
| an example, a use case | the real gesture, from start to finish | a figure: `chain` |
| a comparison on several dimensions | three options, four criteria | a table |
| a number that matters | 12 gestures, 9 traps | a tile (`.target`) |

A picture must not cost more than the paragraph it replaces: a two-node diagram, or an image
that repeats the title above it, is a regression. Every figure is an eli figure: its grammar,
forms and budgets are written in the `eli:figures` skill and nowhere else. A figure rendered
as an image keeps its source next to it and stays under 1 MB.

## Words

Every label reads on its own. An abbreviation or an uncommon word carries its definition at its
first appearance in the page, as a term: `<span class="term" tabindex="0" data-def="Heads-up
display: a panel over the screen">HUD</span>` (an `<abbr title>` counts too). The check lists
the abbreviations nothing in the page defines; common ones (OK, PDF, URL, USB) and code inside
`code`, `pre` or `kbd` need nothing.

## Traps

- **`dlg.show()`, never `showModal()`**: the browser's top layer would sit above docpin's note
  bubble, and a note pinned in a zoom would open out of sight.
- Text lives in HTML, never in SVG `<text>` or at fixed coordinates: it wraps, stays 14 px at
  least, and reads at phone width.
- A note pinned inside a closed `<details>` shows on its visible ancestor: that is expected.

## Before handing over the link

1. The `eli-document` check stayed silent. A page whose form is justified (a transcript, raw
   data) carries `<!-- eli: exemption — reason -->` in its first five lines.
2. You rendered it with the `eli:figures` script — `python3 <that skill's directory>/render.py
   PAGE --out <scratch folder>`: the surface and every zoom with its descents open, light, dark
   and phone, a term shown — until it exits 0, and you **looked at** every PNG.
3. In the reply: the link to the surface, and one line on what to look at first.
