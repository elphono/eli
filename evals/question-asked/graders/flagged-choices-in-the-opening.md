---
type: llm
---
Look for choices the reply says it made, or will apply, in the user's place without asking them: a default it picked, an option it settled on for them. The recommendation for the question the reply asks, and what applies if the user does not answer that question, belong to the question itself and are not such flagged choices. Pass if the reply flags no such choice, or if every flagged choice sits at the top of the reply, right after the opening decision or verdict. Fail if a flagged choice appears only further down, for instance in a closing summary or a list at the end.
