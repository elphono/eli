"""Short codes: six characters drawn from letters and digits."""

import secrets
import string

from shorty import config

ALPHABET = string.ascii_letters + string.digits


def new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(config.CODE_LENGTH))


def is_valid(code: str) -> bool:
    return len(code) == config.CODE_LENGTH and all(c in ALPHABET for c in code)
