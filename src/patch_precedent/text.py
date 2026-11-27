"""Small text helpers shared by styled renderers."""
import re

_SPACED = re.compile(r"\s+[–—]\s+")


def prose(text: str) -> str:
    """Replace en and em dashes in prose with plain hyphens (never applied to verbatim text)."""
    return _SPACED.sub(" - ", text).replace("—", "-").replace("–", "-")
