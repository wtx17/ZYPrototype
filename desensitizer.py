"""Process 6: Sensitive information desensitization before AI ingestion."""

import re

from config import DESENSITIZE_PATTERNS


def desensitize(text: str) -> tuple[str, int]:
    """Apply all desensitization patterns to text. Returns (cleaned_text, change_count)."""
    cleaned = text
    changes = 0
    for pattern, replacement in DESENSITIZE_PATTERNS:
        new_text, count = re.subn(pattern, replacement, cleaned, flags=re.IGNORECASE)
        if count > 0:
            changes += count
            cleaned = new_text
    return cleaned, changes


# Default export the function under a conventional name
sanitize = desensitize
