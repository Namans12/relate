import subprocess
from pathlib import Path

import pytest

from patch_precedent import pins
from patch_precedent.diffparse import read_patch
from patch_precedent.harness import run_case
from patch_precedent.upstream import UpstreamUnavailable, cache_dir, ensure_upstream


def test_missing_cache_offline_message(tmp_path, monkeypatch):
    monkeypatch.setenv("PATCH_PRECEDENT_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("PATCH_PRECEDENT_UPSTREAM_URL", "file:///nonexistent")
    with pytest.raises(UpstreamUnavailable) as e:
        ensure_upstream()
    assert str(cache_dir()) in str(e.value)
    assert "internet" in str(e.value)
    assert "\n" not in str(e.value)
    assert not (tmp_path / "cache" / "relate.git").exists()
    assert [p.name for p in (tmp_path / "cache").iterdir()] == []


@pytest.mark.upstream
def test_run_baseline(tmp_path):
    r = run_case("baseline", None, tmp_path)
    assert r.status == "pass", r.reason
    assert r.exit_code == 0
    assert (r.tap.passed, r.tap.failed) == (194, 0)
    assert r.base_sha == pins.UPSTREAM_SHA
    assert r.command == "sh scripts/tests/test_install_sh.sh"
    assert r.log_path.is_file()
    assert (tmp_path / "baseline.exit").read_text().strip() == "0"
    _assert_no_worktrees()


@pytest.mark.upstream
def test_unappliable_patch_inconclusive(tmp_path):
    p = tmp_path / "bad.patch"
    p.write_text(
        "diff --git a/distribution/install.sh b/distribution/install.sh\n"
        "--- a/distribution/install.sh\n"
        "+++ b/distribution/install.sh\n"
        "@@ -1,3 +1,3 @@\n"
        " this context line does not exist\n"
        "-neither does this one\n"
        "+replacement\n"
        " nor this\n"
    )
    r = run_case("bad", read_patch(p), tmp_path / "run")
    assert r.status == "inconclusive"
    assert "apply" in r.reason
    assert r.tap is None
    assert r.log_path.read_text().strip()
    _assert_no_worktrees()


def _assert_no_worktrees():
    repo = ensure_upstream()
    out = subprocess.run(
        ["git", "--git-dir", str(repo), "worktree", "list"],
        capture_output=True, text=True, check=True,
    ).stdout.strip().splitlines()
    assert len(out) == 1


def _make_source(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ["PATH"],
           "HOME": str(tmp_path)}
    def g(*a):
        return subprocess.run(["git", *a], cwd=src, env=env, check=True,
                              capture_output=True, text=True).stdout.strip()
    g("init", "-q")
    g("config", "uploadpack.allowfilter", "true")
    g("config", "uploadpack.allowanysha1inwant", "true")
    (src / "hello.txt").write_text("hi\n")
    g("add", "hello.txt")
    g("commit", "-q", "-m", "c")
    return src, g("rev-parse", "HEAD")


def test_cache_is_offline_complete_after_ensure(tmp_path, monkeypatch):
    import shutil
    from patch_precedent.upstream import clean_checkout
    src, sha = _make_source(tmp_path)
    monkeypatch.setenv("PATCH_PRECEDENT_CACHE", str(tmp_path / "cache"))
    monkeypatch.setenv("PATCH_PRECEDENT_UPSTREAM_URL", f"file://{src}")
    ensure_upstream(sha)
    shutil.rmtree(src)
    with clean_checkout(sha, tmp_path / "co") as co:
        assert (co / "hello.txt").read_text() == "hi\n"


def test_unwarmed_blobless_cache_offline_raises_unavailable(tmp_path, monkeypatch):
    import shutil
    src, sha = _make_source(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    subprocess.run(["git", "clone", "-q", "--bare", "--filter=blob:none",
                    f"file://{src}", str(cache / "relate.git")], check=True)
    shutil.rmtree(src)
    monkeypatch.setenv("PATCH_PRECEDENT_CACHE", str(cache))
    monkeypatch.setenv("PATCH_PRECEDENT_UPSTREAM_URL", f"file://{src}")
    with pytest.raises(UpstreamUnavailable):
        ensure_upstream(sha)
