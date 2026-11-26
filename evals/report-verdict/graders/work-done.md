---
type: regex
target: {source: file, path: temperature.py}
---
\+\s*32\b[\s\S]*def to_celsius|def to_celsius[\s\S]*\+\s*32\b
