"""Display only the title supported by the expert verification record."""
import re

_PREFIX = re.compile(
    r"^(?:Dr\.?\s*Öğr\.?\s*Üyesi|Arş\.?\s*Gör\.?\s*(?:Dt\.?)?|"
    r"Prof(?:esör)?|Doç(?:ent)?|Doc|Dr|Dt|Uzm(?:an)?(?:\s+Diş\s+Hekimi)?|"
    r"Diş\s+Hekimi|Araştırma\s+Görevlisi)\.?(?:\s+|$)", re.IGNORECASE
)
_TITLES = {
    "Dr. Öğr. Üyesi": "Dr. Öğr. Üyesi",
    "Doç. Dr.": "Doç. Dr.",
    "Prof. Dr.": "Prof. Dr.",
}


def expert_display_name(profile, name):
    """An ORCID number or a name prefix never establishes an academic title."""
    clean = (name or "").strip()
    while True:
        stripped = _PREFIX.sub("", clean, count=1).strip()
        if stripped == clean:
            break
        clean = stripped
    title = _TITLES.get(getattr(profile, "academic_title", "")) if getattr(
        profile, "academic_title_verified", False
    ) else None
    return f"{title or 'Uzm. Dt.'} {clean}".strip()
