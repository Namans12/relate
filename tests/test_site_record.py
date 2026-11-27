import io
import json
import re
from pathlib import Path

from rich.text import Text

from patch_precedent import pins
from patch_precedent.cli import main
from patch_precedent.site.record import TimingSink, ansi_to_spans, scrub
from patch_precedent.tui import StyledReporter, make_console

STYLE_NAMES = {"plain", "accent", "pass", "fail", "strong", "dim"}


def test_ansi_to_spans_maps_palette():
    c = make_console(file=(buf := io.StringIO()), width=100, force_terminal=True,
                     color_system="truecolor")
    # Text.assemble, not `+`: concatenation would make the first style the base of the whole line
    c.print(Text.assemble(("✗ ", "pp.fail"), ("label", "pp.strong"), (" exit 1", "pp.dim")))
    assert ansi_to_spans(buf.getvalue().rstrip("\n")) == [
        ("✗ ", "fail"), ("label", "strong"), (" exit 1", "dim")]


def test_ansi_to_spans_merges_and_resets():
    assert ansi_to_spans("a\x1b[1mb\x1b[0m\x1b[1mc\x1b[0md") == [
        ("a", "plain"), ("bc", "strong"), ("d", "plain")]
    assert ansi_to_spans("\x1b[38;2;217;98;59mx\x1b[39my") == [("x", "accent"), ("y", "plain")]


def test_scrub_removes_local_paths():
    out = scrub(f"{pins.project_root()}/runs/x and {Path.home()}/.cache and /Users/bob/z")
    assert "/Users/" not in out
    assert out.startswith("./runs/x")


def test_timing_sink_stamps_complete_lines():
    s = TimingSink()
    s.write("ab")
    assert s.lines == []
    s.write("c\nd\ne")
    s.write("f\n")
    assert [t for _, t in s.lines] == ["abc", "d", "ef"]
    ts = [t for t, _ in s.lines]
    assert ts == sorted(ts)


def test_styled_output_lines_clean():
    c = make_console(file=(buf := io.StringIO()), width=100, force_terminal=True,
                     color_system="truecolor")
    from rich.panel import Panel
    from rich.table import Table
    g = Table.grid(padding=(0, 1))
    g.add_column(width=10)
    g.add_column()
    g.add_row(Text("ok", style="pp.pass"), Text("x", style="pp.dim"))
    c.print(Panel(Text("hi", style="pp.accent")), width=30)
    c.print(g)
    for line in buf.getvalue().split("\n"):
        assert line == line.rstrip(" ")
        # every line parses independently into known styles
        assert {st for _, st in ansi_to_spans(line)} <= STYLE_NAMES
        stripped = re.sub(r"\x1b\[[0-9;]*m", "", line)
        assert "\x1b" not in stripped


def test_committed_recording_shape():
    rec = json.loads((pins.project_root() / "recorded/demo-all.json").read_text(encoding="utf-8"))
    assert rec["format"] == 1 and rec["overall_exit"] == 0
    labels = {(s, r["label"]) for s, sc in rec["scenarios"].items() for r in sc["runs"]
              if r["patch_id"]}
    assert labels == {("installer", "release-lookup"), ("installer", "token-header"),
                      ("installer", "wording"), ("release", "always-rotate"),
                      ("release", "wording"), ("release", "docs-only")}
    assert "/Users/" not in json.dumps(rec) and str(Path.home()) not in json.dumps(rec)
    th = next(r for r in rec["scenarios"]["installer"]["runs"] if r["label"] == "token-header")
    assert (th["passed"], th["failed"], th["exit_code"], th["failing_numbers"]) == (193, 1, 1, [64])
    assert th["observed"]
    assert rec["transcript"] and all(
        set(s[1] for s in ln["spans"]) <= STYLE_NAMES for ln in rec["transcript"])


def test_recording_has_no_orphan_path_lines():
    rec = json.loads((pins.project_root() / "recorded/demo-all.json").read_text(encoding="utf-8"))
    for ln in rec["transcript"]:
        text = "".join(s[0] for s in ln["spans"])
        if "runs/" in text:
            assert "artifacts" in text or "overall exit" in text, text


def test_cli_record_rejects_base_url(capsys):
    assert main(["site", "record", "--base-url", "https://x.example"]) == 2
    assert "--base-url" in capsys.readouterr().err


def test_cli_record_announces_and_turns_record_error_into_exit_2(tmp_path, monkeypatch, capsys):
    from patch_precedent.site import record as rec

    out = tmp_path / "r.json"
    out.write_text(json.dumps({"elapsed_s": 52.4}))

    def boom(*_a, **_k):
        raise rec.RecordError("expected exactly one new run directory")

    monkeypatch.setattr(rec, "record_demo", boom)
    assert main(["site", "record", "--out", str(out)]) == 2
    err = capsys.readouterr().err
    assert "recording demo all, about 52 s" in err and "expected exactly one" in err
    assert "Traceback" not in err
    out.unlink()
    assert main(["site", "record", "--out", str(out)]) == 2
    assert "about a minute" in capsys.readouterr().err
