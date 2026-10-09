"""Direct-identifier minimization for clinical provider text, not full anonymization."""
import re

_PROVIDER_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+[.][A-Z]{2,}", re.I)
_PROVIDER_TC_RE = re.compile(r"(?<![0-9])[0-9]{11}(?![0-9])")
_PROVIDER_PHONE_RE = re.compile(r"(?<![0-9])(?:[+]?90[ -]?)?(?:0?5[0-9]{2})[ -]?[0-9]{3}[ -]?[0-9]{2}[ -]?[0-9]{2}(?![0-9])")


def redact_direct_identifiers(text: str) -> str:
    # Token-level replacement preserves embedded JSON punctuation and clinical
    # values (tooth numbers, ages, measurements); schemas are not modified.
    for pattern in (_PROVIDER_EMAIL_RE, _PROVIDER_TC_RE, _PROVIDER_PHONE_RE):
        text = pattern.sub('[REDACTED]', text)
    return text
