"""Password rules. The frontend shows the same rules live; the backend is the one that enforces them."""

from __future__ import annotations

import re

PASSWORD_MIN_LENGTH = 8
# bcrypt only uses the first 72 bytes; 64 characters keeps every character meaningful.
PASSWORD_MAX_LENGTH = 64

# Short list of the most common passwords (compared in lower case).
COMMON_PASSWORDS = frozenset({
    "password", "password1", "password123", "contraseña", "contrasena", "12345678", "123456789",
    "1234567890", "qwerty123", "qwertyuiop", "11111111", "abc12345", "iloveyou", "admin123",
    "futbol123", "football", "soccer123", "colombia1", "bienvenido", "welcome1",
})

RULE_MESSAGES = {
    "length": f"Between {PASSWORD_MIN_LENGTH} and {PASSWORD_MAX_LENGTH} characters.",
    "upper": "At least one uppercase letter.",
    "lower": "At least one lowercase letter.",
    "digit": "At least one number.",
    "special": "At least one special character.",
    "no_spaces": "No spaces.",
    "no_personal_data": "Must not contain your name or e-mail.",
    "not_common": "Must not be a common password.",
}


def _personal_fragments(email: str, first_name: str, last_name: str) -> list[str]:
    fragments = [first_name, last_name, email.split("@")[0]]
    return [fragment.strip().lower() for fragment in fragments if len(fragment.strip()) >= 3]


def failed_rules(password: str, *, email: str = "", first_name: str = "", last_name: str = "") -> list[str]:
    """Return the codes of the rules the password breaks (empty list = valid)."""
    lowered = password.lower()
    checks = {
        "length": PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH,
        "upper": any(char.isupper() for char in password),
        "lower": any(char.islower() for char in password),
        "digit": any(char.isdigit() for char in password),
        "special": bool(re.search(r"[^\w\s]|_", password)),
        "no_spaces": not any(char.isspace() for char in password),
        "no_personal_data": not any(fragment in lowered for fragment in _personal_fragments(email, first_name, last_name)),
        "not_common": lowered not in COMMON_PASSWORDS,
    }
    return [rule for rule, passed in checks.items() if not passed]
