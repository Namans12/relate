"""Patch identity and changed files, parsed from `diff --git` headers."""
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

_HEADER = re.compile(r"^diff --git a/(?P<a>.+?) (?:b/(?P<b>.+)|(?P<null>/dev/null))$")


@dataclass(frozen=True)
class PatchInfo:
    path: Path
    label: str
    sha256: str
    id: str
    changed_files: tuple[str, ...]
    patch_key: str


def header_path(line: str) -> str | None:
    """The file a `diff --git` header line names, or None if it is not a header."""
    m = _HEADER.match(line.rstrip())
    if not m:
        return None
    name = m.group("a") if m.group("null") else m.group("b")
    return m.group("a") if name == "/dev/null" else name


def changed_files_from_text(text: str) -> tuple[str, ...]:
    seen: list[str] = []
    for line in text.splitlines():
        name = header_path(line)
        if name is not None and name not in seen:
            seen.append(name)
    return tuple(seen)


def read_patch(path: Path) -> PatchInfo:
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    from .identity import patch_key  # identity imports this module
    text = data.decode("utf-8", errors="replace")
    return PatchInfo(path, path.stem, sha, "patch:" + sha[:12],
                     changed_files_from_text(text), patch_key(text))
