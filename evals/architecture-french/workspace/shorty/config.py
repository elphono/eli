"""Settings read once at start-up."""

import os

DATABASE = os.environ.get("SHORTY_DB", "shorty.sqlite3")
PORT = int(os.environ.get("SHORTY_PORT", "8080"))
CODE_LENGTH = 6
FLUSH_EVERY = 50  # clicks counted in memory before they are written to the database
