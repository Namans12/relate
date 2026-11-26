"""Whitespace-insensitive patch key, for evidence lookup only."""
import hashlib
import re


def patch_key(text: str) -> str:
    """Key a diff by its content with all whitespace removed.

    Tabs, spaces, CRLF and trailing whitespace cannot change the key, so a diff that
    an agent passes through a tool still finds its replay. This identifies the patch
    for evidence lookup only; verdict identity in the demo stays the byte sha256.
    """
    lines = (re.sub(r"\s+", "", line) for line in text.splitlines())
    normalised = "\n".join(line for line in lines if line)
    return "pk:" + hashlib.sha256(normalised.encode()).hexdigest()[:16]
