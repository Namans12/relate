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


def _changed_files(text: str) -> tuple[str, ...]:
    seen: list[str] = []
    for line in text.splitlines():
        m = _HEADER.match(line)
        if not m:
            continue
        name = m.group("a") if m.group("null") else m.group("b")
        if name == "/dev/null":
            name = m.group("a")
        if name not in seen:
            seen.append(name)
    return tuple(seen)


def read_patch(path: Path) -> PatchInfo:
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    text = data.decode("utf-8", errors="replace")
    return PatchInfo(path, path.stem, sha, "patch:" + sha[:12], _changed_files(text))
