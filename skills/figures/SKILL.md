---
name: figures
description: Draw a figure (a diagram, schema, flowchart, sketch or infographic) as a self-contained HTML page at two or three ELI levels, where a shape says what sort of thing a node is and a colour says who acts. Use it whenever the user asks for a drawing, a diagram, a schema, a chart of steps or an infographic, in any language (dessin, schema, diagramme, croquis, Zeichnung, Skizze, dibujo, esquema, disegno...), and whenever an explanation needs a diagram that branches, loops or has more than five nodes. Not for charts of data values.
---

# ELI figures

A figure is a page of its own: one subject, drawn at two or three levels, one visible at a time.
The levels and the writing rules live in the `eli` output style; this skill says how to decide
what to draw, how to draw it, and how to check it. Work through the eight steps in order.

## 1. Write the brief first

Before any markup, write these four lines down (in your reply's working notes, not in the page):

1. **The message**: the one sentence the figure must make obvious. If you need two, you need two figures.
2. **The reader and the level** asked for (ELI-lambda when nothing says otherwise).
3. **The form**, from the table of step 2.
4. **The distribution**: every candidate element (step, actor, number, exception, safeguard), and
   for each level whether it is **shown**, **merged** into another node, or **hidden**, and where a
   hidden one goes: the level below, a term's definition, or nowhere.

| Element | ELI-lambda | ELI-initiate | ELI-Architect | Hidden goes to |
|---|---|---|---|---|
| "the system checks the input" | merged into "it prepares" | shown | shown, with the component | |
| a rare error case | hidden | note | shown | ELI-initiate |
| an internal file name | hidden | hidden | hidden | nowhere |

## 2. Choose the form

| What the message says | Form | Drawn as |
|---|---|---|
| a sequence: this, then this, then this | `chain` | nodes joined by arrows, left to right |
| a fork: depending on one question, it goes one way or another | `branch` | a question, then one row per path |
| a repetition: the last step leads back to the first | `cycle` | a chain with a return arrow |
| a hand-off between actors, in order | `lanes` | one column per actor, time running down |
| a structure: parts and what passes between them | `map` | rows of parts, labelled links between rows |

A comparison (options against criteria) is not a figure: it stays a table. A single number is a
sentence. Two nodes are a sentence too.

## 3. What each level shows and hides

Ask of every element: **would the reader miss it if it were gone?** If not, hide it. If only
someone one level down would, move it there. What is shown, the reader must be able to act on.

| Level | Shows | Hides | Nodes, at most |
|---|---|---|---|
| ELI-lambda | the promise and the path a person sees; durations a person feels | mechanisms, component names, exceptions | 9 |
| ELI-initiate | the mechanisms that make it work; what works, what does not yet; safeguards | components, formats, file names | 12 |
| ELI-Architect | the components and their flows, the numbers that constrain, the trade-off | code, function names | 15 |

- A node label is **8 words at most**; a sub-line adds a number or a condition, not a sentence.
- Around the figure: one lead sentence above it, at most one short paragraph below it.
- Over budget: merge nodes, move detail down a level, or split into two figures.
- render.py refuses more than 15 nodes in one figure, and notes a panel over its budget.

## 4. The visual grammar

A **shape says what sort of thing** a node is (`data-node`); a **colour says who acts, or which
path** (`data-tone`). Both keep the same meaning at every level of a page.

| Kind | Shape | Is |
|---|---|---|
| `actor` | a round badge with a pictogram | who acts: a person, a part of the system |
| `action` | a card | something done, a step |
| `question` | a hexagon | a choice that opens paths |
| `store` | a cylinder | what is kept: a catalogue, a memory, a file |
| `result` | a filled pill | what the reader gets in the end |
| `note` | a dashed card | an aside, a safeguard, a limit |

| Tone | Means |
|---|---|
| `you` | the reader, the person the figure speaks to |
| `sys` | the system the figure is about |
| `key` | a second actor, or the slow or costly path |
| `ok` | an outcome that is good or confirmed |
| `muted` | background, outside, not yet |

- **The figure is its own legend**: labels sit on the nodes and the arrows, never in a key box
  apart. A path's colour is named on its answer chip ("Yes: known recipe").
- **Colour never carries a distinction alone**: the shape, a label or a pictogram says it too.
- **Not austere**: soft fills, rounded shapes, a pictogram per node that has an actor, a clear
  hierarchy of sizes (title, sub-line). **Never decorative**: a colour or a shape that does not
  carry a distinction is removed.

## 5. The text

- Every label reads **on its own**, as a whole phrase: "The server builds the recipe", not "build".
- An abbreviation or an uncommon word carries its definition at its **first appearance in each
  level**: `<span class="term" tabindex="0" data-def="the definition">word</span>`. The definition
  shows on hover, keyboard focus and tap. A common word needs none.
- Write in the reader's language. Keep technical words as the code, the tools and the people
  who use them write them (`HUD`, `commit`, `timeout`); translate only what is said translated.
- Numbers come with their unit and, when measured, their range: "2 to 7 s", not "fast".
- No opaque reference: no ticket number, no bare file name at ELI-lambda or ELI-initiate.

## 6. Build it

1. Copy `template.html` (next to this file) to the page's place, set `<html lang>`, and replace
   every sample, the labels of the level selector included.
2. Take each figure's markup from `forms.html`, which shows every form and every shape.
3. Keep the contract the page and render.py rely on:

| Element | Carries |
|---|---|
| the root of a figure | `<figure data-figure="chain|branch|cycle|lanes|map">` |
| a node | `data-node="<kind>"`, a kind of step 4; `data-tone` on it or on its path |
| a level panel | `data-eli="lambda|initiate|architect"`, `id="eli-<level>"`; `data-open` on the one asked for |
| the TL;DR | `data-tldr`, above the level selector: one to three sentences that are enough alone |
| a term | `class="term" tabindex="0" data-def="..."` |

- ELI-lambda and ELI-initiate always; ELI-Architect when it is asked for or the subject has
  components. `#eli-<level>` in the URL opens that level.
- Text lives in HTML elements laid out by grid or flex, so it wraps and never overflows. Inline
  SVG draws pictograms only: **no SVG `<text>`**, no text placed by coordinates.
- The CSS between `/* eli-figures:start */` and `/* eli-figures:end */` is shared: never edit it
  in a page. Page-specific rules go after it.
- No network: no script, font or image from outside. Light and dark follow the system.

## 7. The render loop

```bash
python3 <this skill's directory>/render.py PAGE --out <scratch folder>
```

It captures every level at 1400x900 light, 1400x900 dark and 390x844 light, and a term's
definition shown, then prints one table of measures per level and one line per defect: sideways
scrolling, cut text, overlapping nodes, text under 14 px, more than 15 nodes, a shape or form
outside the lists, SVG text, a definition that does not show. Exit code 0: no defect; 1:
defects; 3: it cannot render (it says how to install Playwright and Chromium).

Then **open every PNG** and critique it against this list, writing down what you see:

1. Does a node touch, cover or crowd another? Is any label cut or squeezed?
2. Does every arrow leave the right node and arrive at the right one, pointing the right way?
3. Hierarchy: does the eye land first on the message, then on the paths?
4. Can each label be read alone, at its size, without the paragraph?
5. Light and dark: is every colour still distinct, every fill still readable?
6. Phone: does each form read top to bottom, with nothing too narrow to read?
7. The term capture: does the definition show whole, inside the screen?
8. Budgets: nodes and words per level, labels of 8 words at most.

Fix, render again. **Two passes at least**, and until the exit code is 0 and the list is clean.

## 8. Hand it over

- The page goes under `docs/<yyyy-mm-dd>-<subject>.html` of the project the user works in.
- The reply in the terminal holds a TL;DR, the link with the level asked for (`...html#eli-lambda`),
  and the level line of the `eli` style. The figure is in the page, not in the terminal.
- If docpin is installed, its `docpin:annotatable-documents` skill says how to give the link and
  wait for notes.
