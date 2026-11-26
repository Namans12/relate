"""Fetch and verify Relate's own CLI binary, and build its MCP server config (docs only)."""
import hashlib
import os
import platform
import urllib.request
from pathlib import Path
from typing import Callable

from .upstream import cache_dir

VERSION = "1.3.0"
ASSET = "relate-darwin-arm64"
URL = f"https://github.com/relatedb/relate/releases/download/v{VERSION}/{ASSET}"
SHA256 = "b1d2d2f59fca696b0c2df35364c8a198a317b6fa733f0b8ff21b8fdcb7e30bc6"


class RelateCliError(RuntimeError):
    """The relate CLI could not be fetched or verified."""


def _supported_platform() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def relate_cli_path() -> Path:
    return cache_dir() / f"relate-cli-{VERSION}" / ASSET


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path) -> None:
    if not url.startswith("https://"):
        raise RelateCliError(f"refusing non-https download URL {url}")
    with urllib.request.urlopen(url, timeout=120) as resp, open(dest, "wb") as out:
        while chunk := resp.read(1 << 20):
            out.write(chunk)


def ensure_relate_cli(fetch: Callable[[str, Path], None] | None = None) -> Path:
    """Path of the verified relate CLI, downloading it first if absent or corrupt."""
    if not _supported_platform():
        raise RelateCliError("relate CLI fetch supports macOS arm64 only")
    target = relate_cli_path()
    if target.is_file() and _sha256(target) == SHA256:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{ASSET}.tmp-{os.getpid()}")
    try:
        (fetch or _download)(URL, tmp)
        got = _sha256(tmp)
        if got != SHA256:
            raise RelateCliError(
                f"relate CLI sha256 mismatch: expected {SHA256}, got {got}; file deleted")
        tmp.chmod(0o755)
        os.replace(tmp, target)
    except BaseException:
        tmp.unlink(missing_ok=True)
        if target.is_file() and _sha256(target) != SHA256:
            target.unlink()
        raise
    return target


def relate_mcp_config(store_copy: Path, cli: Path | None = None) -> dict:
    """Relate's native read-only MCP server over a copy of the store (docs, smoke test)."""
    cli = cli if cli is not None else ensure_relate_cli()
    return {"mcpServers": {"relate": {"command": str(cli), "args": [
        "serve", "--mcp", "stdio", "--read-only", "--database", str(store_copy)]}}}
