import hashlib
import os
import subprocess
import sys

from patch_precedent.cli import main
from patch_precedent.pins import STORE_PATH, project_root
from patch_precedent.report import render_evidence_chain
from patch_precedent.tap import TapResult

FIXTURES = project_root() / "fixtures" / "installer"
RELEASE = FIXTURES / "release-lookup.patch"
WORDING = FIXTURES / "wording.patch"


def _row(check, number, kind="static"):
    return {
        "file": "a.sh", "decision": "ADR-1", "title": "T", "status": "Proposed",
        "rule": "r", "reason": "because " * 30, "decision_url": "http://d",
        "citation_url": "http://c", "consequences_url": "http://s",
        "implementation": "0123456789abcdef", "commit_subject": "subj",
        "commit_url": "http://m", "check": check, "check_kind": kind,
        "check_number_at_pin": number, "check_url": f"http://k{number}",
        "check_evidence": "e",
    }


def test_explain_release_lookup(capsys):
    assert main(["explain", str(RELEASE)]) == 0
    out = capsys.readouterr().out
    assert "distribution/install.sh" in out
    assert "ADR-0585" in out
    assert "drift guard: install.sh consults no GitHub API endpoint (ADR-0585)" in out
    assert "no case made a GitHub API request (ADR-0585)" in out
    assert "5ac38808" in out
    assert "60" in out
    assert "mode     read-only: no upstream fetch, no patch executed" in out
    assert "(sha256 635b00b21f4b)" in out


def test_explain_wording_same_chain(capsys):
    main(["explain", str(RELEASE)])
    a = capsys.readouterr().out.split("\n\n", 1)[1]
    main(["explain", str(WORDING)])
    b = capsys.readouterr().out.split("\n\n", 1)[1]
    assert a == b


def test_explain_unlinked(tmp_path, capsys):
    p = tmp_path / "x.patch"
    p.write_text("diff --git a/README.md b/README.md\n--- a/README.md\n+++ b/README.md\n@@ -1 +1 @@\n-a\n+b\n")
    assert main(["explain", str(p)]) == 0
    assert "README.md: no linked decision" in capsys.readouterr().out


def test_explain_no_changed_files(tmp_path, capsys):
    p = tmp_path / "e.patch"
    p.write_text("nothing here\n")
    assert main(["explain", str(p)]) == 0
    assert "no changed files found in patch" in capsys.readouterr().out


def test_explain_offline(tmp_path):
    code = (
        "import sys\n"
        "from patch_precedent.cli import main\n"
        f"rc = main(['explain', {str(RELEASE)!r}])\n"
        "print('LOADED', 'patch_precedent.upstream' in sys.modules,"
        " 'patch_precedent.harness' in sys.modules)\n"
        "sys.exit(rc)\n"
    )
    env = dict(os.environ, PATCH_PRECEDENT_CACHE=str(tmp_path / "does-not-exist"))
    r = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "LOADED False False" in r.stdout
    assert not (tmp_path / "does-not-exist").exists()


def test_explain_store_unchanged(capsys):
    before = hashlib.sha256(STORE_PATH.read_bytes()).hexdigest()
    main(["explain", str(RELEASE)])
    assert hashlib.sha256(STORE_PATH.read_bytes()).hexdigest() == before


def test_explain_missing_file_exit_2(tmp_path, capsys):
    assert main(["explain", str(tmp_path / "nope.patch")]) == 2
    cap = capsys.readouterr()
    assert cap.err.count("\n") == 1 and "Traceback" not in cap.err


def test_explain_missing_store_exit_2(tmp_path, capsys):
    assert main(["explain", str(RELEASE), "--store", str(tmp_path / "no.rl")]) == 2
    cap = capsys.readouterr()
    assert cap.err.count("\n") == 1 and "Traceback" not in cap.err


def test_render_observed():
    rows = [_row("name7", 7), _row("name193", 193, "runtime")]
    out = render_evidence_chain("a.sh", rows, {"name7": TapResult(7, False, "name7", False)})
    assert "→ not ok 7" in out
    assert "→ not observed" in out
    ok = render_evidence_chain("a.sh", rows[:1], {"name7": TapResult(7, True, "name7", False)})
    assert "→ ok 7" in ok


def test_render_no_rows():
    assert render_evidence_chain("a.sh", []) == "a.sh: no linked decision"
