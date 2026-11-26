"""Upstream bare-repo cache and clean per-run checkouts."""
import contextlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Iterator

from . import pins


class UpstreamUnavailable(RuntimeError):
    """The upstream repository could not be obtained."""


def cache_dir() -> Path:
    env = os.environ.get("PATCH_PRECEDENT_CACHE")
    return Path(env) if env else Path.home() / ".cache" / "patch-precedent"


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )


def _has_commit(repo: Path, sha: str) -> bool:
    r = subprocess.run(
        ["git", "--git-dir", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True,
    )
    return r.returncode == 0


def ensure_upstream(sha: str = pins.UPSTREAM_SHA) -> Path:
    url = os.environ.get("PATCH_PRECEDENT_UPSTREAM_URL") or pins.UPSTREAM_URL
    root = cache_dir()
    repo = root / "relate.git"
    unavailable = UpstreamUnavailable(
        f"upstream cache {repo} is missing or incomplete; "
        f"the first run needs internet access to fetch {url}"
    )
    try:
        if not repo.is_dir():
            root.mkdir(parents=True, exist_ok=True)
            tmp = root / f"relate.git.tmp-{os.getpid()}"
            shutil.rmtree(tmp, ignore_errors=True)
            try:
                _git("clone", "--bare", "--filter=blob:none", url, str(tmp))
                os.rename(tmp, repo)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        if not _has_commit(repo, sha):
            _git("--git-dir", str(repo), "fetch", "origin", sha)
        if not _has_commit(repo, sha):
            raise unavailable
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
        raise unavailable from exc
    return repo


@contextlib.contextmanager
def clean_checkout(sha: str, dest: Path) -> Iterator[Path]:
    repo = ensure_upstream(sha)
    gd = str(repo)
    dest = Path(dest).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    _git("--git-dir", gd, "worktree", "prune")
    _git("--git-dir", gd, "worktree", "add", "--detach", str(dest), sha)
    try:
        head = _git("rev-parse", "HEAD", cwd=dest).stdout.strip()
        assert head == sha, f"checkout HEAD {head} != {sha}"
        dirty = _git("status", "--porcelain", cwd=dest).stdout
        assert not dirty.strip(), f"checkout not clean: {dirty}"
        yield dest
    finally:
        subprocess.run(
            ["git", "--git-dir", gd, "worktree", "remove", "--force", str(dest)],
            capture_output=True,
        )
        shutil.rmtree(dest, ignore_errors=True)
        subprocess.run(
            ["git", "--git-dir", gd, "worktree", "prune"], capture_output=True
        )
