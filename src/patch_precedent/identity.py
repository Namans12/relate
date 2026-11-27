"""Patch key from a diff's changed lines only, for evidence lookup."""
import hashlib
import re

from .diffparse import header_path


def patch_key(text: str) -> str:
    """Key a diff by its added and removed lines, per file, ignoring all whitespace.

    Context lines, hunk headers, index lines and whitespace (tabs, CRLF, trailing)
    cannot change the key, so a diff an agent trims or re-wraps still finds its replay.
    This identifies the patch for evidence lookup only; verdict identity in the demo
    stays the byte sha256.
    """
    path = ""
    out: list[str] = []
    for line in text.splitlines():
        name = header_path(line)
        if name is not None:
            path = name
            continue
        if line[:1] not in ("+", "-") or line.startswith(("+++ ", "--- ")):
            continue
        body = re.sub(r"\s+", "", line[1:])
        if body:
            out.append(f"{path}\t{line[0]}{body}")
    return "pk:" + hashlib.sha256("\n".join(out).encode()).hexdigest()[:16]
