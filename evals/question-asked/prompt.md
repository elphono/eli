---
description: A question put to the user opens on the decision as a level-1 heading in capitals, draws its options as a fork in a code block, asks one decision only, carries no 80/20 section, and flags any choice made for the user in its opening
max_turns: 5
timeout_seconds: 300
allowed_tools: [Read, Glob, Grep, Skill, Write, Edit]
runs: 3
---

I'm adding an offline mode to the small to-do app my team uses (a web app, about two hundred users). Three things are still open: what happens when two devices change the same task while offline, how long deleted tasks are kept before they are purged, and whether a user can stay signed in on several devices at once. Don't build anything yet: tell me what you need from me.
