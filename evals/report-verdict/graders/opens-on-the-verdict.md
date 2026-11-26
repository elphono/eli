---
type: llm
---
Read only the first sentence of the reply, after any leading "TL;DR" label. Pass if that sentence is a verdict on the work that was asked for: it says whether the work is done, not done or done in part (for instance "Done: ...", "Fixed: ...", "I fixed the conversion ...", "The conversion is fixed and both functions are documented."); it need not list every part of the work. Fail if the reply opens on anything else before such a verdict: a preamble, a heading that is not the verdict, what was read or searched, how the bug was found, an explanation of the bug's cause, or a list of steps.
