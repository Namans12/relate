import pytest

from patch_precedent import harness, pins, upstream
from patch_precedent.cli import main
from patch_precedent.demo import run_all, run_demo
from patch_precedent.report import overall_exit


def test_missing_fixtures_dir_prints_no_header(tmp_path, capsys):
    assert run_demo("installer", fixtures_dir=tmp_path / "nope", runs_root=tmp_path) == 2
    cap = capsys.readouterr()
    assert cap.out == ""
    assert "fixtures directory not found" in cap.err


def test_missing_store_is_one_line_exit_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pins, "STORE_PATH", tmp_path / "absent.rl")
    assert run_demo("installer", runs_root=tmp_path) == 2
    cap = capsys.readouterr()
    assert cap.out == ""
    assert len(cap.err.strip().splitlines()) == 1
    assert "absent.rl" in cap.err


def test_unreachable_upstream_before_header(tmp_path, monkeypatch, capsys):
    def boom():
        raise upstream.UpstreamUnavailable("cache missing; first run needs internet")

    monkeypatch.setattr(upstream, "ensure_upstream", boom)
    assert run_demo("installer", runs_root=tmp_path) == 4
    cap = capsys.readouterr()
    assert cap.out == ""
    assert "first run needs internet" in cap.err


def test_upstream_lost_mid_run_is_exit_4_no_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(upstream, "ensure_upstream", lambda: None)

    def boom(*a, **k):
        raise upstream.UpstreamUnavailable("upstream vanished")

    monkeypatch.setattr(harness, "run_case", boom)
    assert run_demo("installer", runs_root=tmp_path) == 4
    cap = capsys.readouterr()
    assert "upstream vanished" in cap.err
    assert "Traceback" not in cap.err


def test_run_all_missing_store_fails_cleanly(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pins, "STORE_PATH", tmp_path / "absent.rl")
    assert run_all(runs_root=tmp_path) == 2
    cap = capsys.readouterr()
    assert cap.out == ""
    assert "absent.rl" in cap.err
    assert list(tmp_path.iterdir()) == []


def test_run_all_upstream_unreachable_before_output(tmp_path, monkeypatch, capsys):
    def boom():
        raise upstream.UpstreamUnavailable("cache missing; first run needs internet")

    monkeypatch.setattr(upstream, "ensure_upstream", boom)
    assert run_all(runs_root=tmp_path) == 4
    assert capsys.readouterr().out == ""


def test_demo_all_rejects_fixtures(tmp_path, capsys):
    assert main(["demo", "all", "--fixtures", "x"]) == 2
    cap = capsys.readouterr()
    assert cap.out == ""
    assert len(cap.err.strip().splitlines()) == 1


def test_overall_exit_precedence():
    assert overall_exit([0, 0]) == 0
    assert overall_exit([0, 3]) == 3
    assert overall_exit([3, 2]) == 2
    assert overall_exit([2, 3, 0]) == 2
    assert overall_exit([0, 4, 2]) == 4
    assert overall_exit([]) == 0
