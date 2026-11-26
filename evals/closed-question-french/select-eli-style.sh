#!/usr/bin/env bash
# Select the eli output style in the run's user settings, as a user does after installing
# the plugin (README, "Install", step 2). The harness starts Claude with
# --setting-sources user, and those settings live in the run's config directory, next to
# HOME. The harness has created that directory (with its .claude.json) before this script
# runs, and merges its own keys into settings.json afterwards. A case that grants Bash cannot
# use this script: the harness then creates settings.json itself, exclusively, and the run
# fails on the file this script left. Both arms get the same
# settings: only the plugin differs between them. The style-active grader of each case
# checks that the session did start with the style.
# A case that needs files in the session's working directory (a project to read, a file to
# fix) keeps them in a workspace/ folder next to this script: the harness runs the script
# in that directory, and the files are copied there, before the session starts.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
config="$HOME/../config"
if [ ! -f "$config/.claude.json" ]; then
  echo "no run config directory at $config: the eval harness layout changed" >&2
  exit 1
fi
python3 - "$config/settings.json" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as f:
        settings = json.load(f)
except FileNotFoundError:
    settings = {}
settings["outputStyle"] = "eli:eli"
with open(path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)
PY
if [ -d "$here/workspace" ]; then
  cp -R "$here/workspace/." .
fi
