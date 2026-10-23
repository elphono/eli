---
name: documents
description: Give a document that explains or reports (spec, design note, report, comparison, procedure, review) the ELI form — an ELI-lambda surface whose every element opens on click into an ELI-initiate zoom, each zoom leading down to ELI-Architect, with occasional ELI-Tech inserts. Use it for every HTML document meant for a human reader, starting from the template next to this file.
---

# ELI documents

The levels, the inference table and the forms live in the `eli` output style. This skill says
how a **document** carries them. If docpin is installed, its `docpin:annotatable-documents`
skill gives the mechanics — where to write the document, how to hand over the link, how to wait
for and answer notes: follow both.

## The model

```
surface ── ELI-lambda
  promise title · one sentence · 3 to 5 illustrated elements (steps, loop, "done" strip)
    │ click on an element
    ▼
zoom ── ELI-initiate
  the mechanisms that make the idea possible and convenient, drawn; what works, what not yet
    │ "Under the hood", at the bottom of EVERY zoom
    ▼
descent ── ELI-Architect
  components and flows (diagram), the number that constrains, options and trade-off (table)
    │ ⚙ only where a precise point calls for it
    ▼
insert ── ELI-Tech
  file, function, command, short excerpt
```

ELI5 has no floor in a document.

## Start from the template

Copy `template.html`, which sits in this skill's directory, to the document's place — for
instance `docs/<yyyy-mm-dd>-<subject>.html` — then replace **every** sample text. The template
is light and dark, reads at phone width and opens from the keyboard; it is resized without
being rewritten:

| To | Do |
|---|---|
| have fewer steps | remove the card, its `.next` arrow, its `<dialog>`; adjust `.s1….s4` |
| a subject that is not a loop | remove `.ret-path` and `.ret`, and the `z-loop` zoom |
| nothing done to show | remove `.proof` and the `z-done` zoom |
| one more ELI-Tech insert | copy a `details.tech` into the descent that needs it, with a new `id` |

Write the page in the reader's language: set `<html lang>` and translate the template's
labels ("Under the hood", "Close", the level ladder) along with the samples.

## The convention, attribute by attribute

| Element | Carries | Role |
|---|---|---|
| the surface's `<main>` | `data-eli="lambda"` | the entry level |
| each clickable element | `data-zoom="z-…"`, `role="button"`, `tabindex="0"` | opens the zoom with the same `id` |
| each `<dialog class="zoom">` | `data-eli="initiate"`, `id="z-…"` | one notch of detail |
| a `<details class="descent">` in **every** zoom | `data-eli="architect"`, `id="a-…"` | "Under the hood" |
| a `<details class="tech">`, inside a descent | `data-eli="tech"`, `id="t-…"` | one precise point of code |
| a link to a level | `<a href="#t-…">` (or `#z-…`, `#a-…`) | opens the zoom and the descents that lead to the target |

`id`s are unique. A link ending in `#a-2` opens the descent of zoom 2 directly: that is what to
give in the terminal to point at a precise level. docpin anchors a note on the first `id` it
meets going up, which keeps the note in place when the document changes.

## What each floor holds

| Floor | Holds | Does not hold |
|---|---|---|
| ELI-lambda surface | the promise; one "who does what" sentence; each step = a title, a visual, a sentence with no jargon; the state ("works", "in progress") | mechanism, component name, technical number |
| ELI-initiate zoom | the mechanism as a chain or a diagram; "what works / not yet"; each new word defined | format, protocol, file name |
| ELI-Architect descent | a diagram of the components and their flows; the number that constrains; a table of options and the trade-off | code, function names |
| ELI-Tech insert | path, signature, command, short excerpt; the edge case | a lecture |

## What calls for a picture

In a document, an idea is **drawn first**; prose keeps only what does not draw — a trade-off, a
doubt, a nuance. The test is not length but the presence of something to understand:

| The passage carries | Example | Form |
|---|---|---|
| a concept, a notion of the project | what a "lease" or a "recipe" is | annotated SVG diagram |
| a mechanism | what happens when the resource is already taken | diagram, before/after |
| a flow between several actors | who writes what, in which order, where | swimlanes, sequence |
| an example, a use case | the real gesture, from start to finish | numbered route |
| a comparison on several dimensions | three options, four criteria | table, coloured matrix |
| a number that matters | 12 gestures, 9 traps | tile, gauge, bar |

A picture must not cost more than the paragraph it replaces: a two-node diagram, or an image
that repeats the title above it, is a regression.

Figures are **sober**: what is made to stop a scrolling thumb is not made to be read. Light
background (dark follows the system), few colours, **each one carrying a distinction**,
saturated enough to tell apart at a glance — monochrome is not neutral, it is dull. A figure
rendered as an image keeps its source next to it, so it is edited rather than redone, and stays
light: render it at scale 1, under 1 MB.

## Traps

- **`dlg.show()`, never `showModal()`**: the browser's top layer would sit above docpin's note
  bubble, and a note pinned in a zoom would open out of sight.
- The text of a figure reads at its **displayed** size: a 1080 px image shown at 500 px halves
  its type. Aim for 14 px displayed at least; the template draws architecture diagrams
  vertically, with a narrow `viewBox`, so they stay legible on a phone.
- A note pinned inside a closed `<details>` shows on its visible ancestor: that is expected.

## Before handing over the link

1. The `eli-document` check stayed silent. A page whose form is justified (a transcript, raw
   data) carries `<!-- eli: exemption — reason -->` in its first five lines.
2. You **looked at the rendered page** — light, dark, at phone width — and opened at least one
   zoom and its descent.
3. In the reply: the link to the surface, and one line on what to look at first.
