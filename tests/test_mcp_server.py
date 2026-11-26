import hashlib
import json
import os
import subprocess
import sys
import threading

import pytest

from patch_precedent import pins
from test_evidence import _make_replays, _text

DESCRIPTION = (
    "Given a unified diff against relatedb/relate at the pinned commit, returns the "
    "architectural decisions (ADRs) governing each changed file, their rules and reasons, "
    "the regression checks that guard them, and each check's observed result from Patch "
    "Precedent's replay of this exact patch. Read-only.")
INSTRUCTIONS = ("Call precedent_for_patch with the full unified diff to get the decisions, "
                "checks and observed replay results behind the changed files.")
TIMEOUT = 60


class Session:
    """A real stdio MCP server subprocess driven with newline-delimited JSON-RPC."""

    def __init__(self, runs, store=pins.STORE_PATH):
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "patch_precedent.cli", "mcp", "--store", str(store),
             "--runs-dir", str(runs)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", env=dict(os.environ))
        self.stdout_lines: list[str] = []
        self._id = 0
        # a hung server must fail the test, not hang it
        self._timer = threading.Timer(TIMEOUT, self.proc.kill)
        self._timer.start()

    def send(self, msg):
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params=None):
        self._id += 1
        self.send({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})
        while True:
            line = self.proc.stdout.readline()
            assert line, "server closed stdout (hung or crashed)"
            self.stdout_lines.append(line)
            msg = json.loads(line)
            if msg.get("id") == self._id:
                return msg

    def initialize(self):
        res = self.request("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "0"}})
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return res["result"]

    def call(self, diff):
        return self.request("tools/call", {"name": "precedent_for_patch",
                                           "arguments": {"diff": diff}})["result"]

    def close(self):
        if self.proc.stdout.closed:
            return
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self._timer.cancel()
        self.stdout_lines += self.proc.stdout.read().splitlines()
        self.stderr = self.proc.stderr.read()
        self.proc.stdout.close()
        self.proc.stderr.close()


@pytest.fixture
def server(tmp_path):
    runs = tmp_path / "runs"
    _make_replays(runs)
    s = Session(runs)
    s.runs = runs
    yield s
    s.close()


def _checks(result):
    payload = json.loads(result["content"][0]["text"])
    return {c["number_at_pin"]: c["observed"]
            for f in payload["files"] for d in f["decisions"] for c in d["checks"]}, payload


def test_tools_list(server):
    init = server.initialize()
    assert init["instructions"] == INSTRUCTIONS
    tools = server.request("tools/list")["result"]["tools"]
    assert [t["name"] for t in tools] == ["precedent_for_patch"]
    (t,) = tools
    assert t["description"] == DESCRIPTION
    assert t["annotations"]["readOnlyHint"] is True
    assert t["annotations"]["openWorldHint"] is False
    assert t["inputSchema"]["required"] == ["diff"]
    assert t["inputSchema"]["properties"]["diff"]["type"] == "string"


def test_tool_call_c1(server):
    server.initialize()
    res = server.call(_text("installer", "release-lookup"))
    assert not res.get("isError")
    assert len(res["content"]) == 1 and res["content"][0]["type"] == "text"
    checks, payload = _checks(res)
    assert checks == {7: "not ok", 193: "not ok", 64: "ok"}
    assert payload["replay"]["label"] == "release-lookup"


def test_tool_call_no_replay_hint(tmp_path):
    s = Session(tmp_path / "no-runs")
    try:
        s.initialize()
        res = s.call(_text("installer", "release-lookup"))
        checks, payload = _checks(res)
        assert set(checks.values()) == {"not observed"} and payload["replay"] is None
        assert "demo all" in payload["hint"] and str(tmp_path / "no-runs") in payload["hint"]
        assert payload["files"][0]["decisions"][0]["id"] == "ADR-0585"
    finally:
        s.close()


@pytest.mark.parametrize("arguments", [{"diff": ""}, {"diff": "   \n"}, {"diff": 5}])
def test_tool_error_is_clean(server, arguments):
    server.initialize()
    res = server.request("tools/call", {"name": "precedent_for_patch",
                                        "arguments": arguments})["result"]
    assert res["isError"] is True
    text = res["content"][0]["text"]
    assert text == "diff must be a non-empty unified diff"
    assert "Traceback" not in text and "\n" not in text


def test_missing_argument_is_an_error(server):
    server.initialize()
    res = server.request("tools/call", {"name": "precedent_for_patch", "arguments": {}})["result"]
    assert res["isError"] is True and "Traceback" not in res["content"][0]["text"]


def test_tool_exception_is_one_line(tmp_path):
    bad = tmp_path / "bad.rl"
    bad.write_bytes(b"garbage" * 100)
    s = Session(tmp_path / "runs", store=bad)
    try:
        s.initialize()
        res = s.call(_text("installer", "release-lookup"))
        assert res["isError"] is True
        text = res["content"][0]["text"]
        assert "Traceback" not in text and "\n" not in text and text
    finally:
        s.close()


def test_server_never_writes(server):
    paths = [pins.STORE_PATH, *server.runs.rglob("replay.rl")]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    server.initialize()
    server.call(_text("installer", "release-lookup"))
    server.call(_text("release", "docs-only"))
    server.call("")
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths} == before


def test_stdout_is_protocol_only(server):
    server.initialize()
    server.request("tools/list")
    server.call(_text("installer", "token-header"))
    server.call("")
    server.close()  # also collects anything written after the last response
    assert len(server.stdout_lines) >= 4
    for line in server.stdout_lines:
        msg = json.loads(line)
        assert msg["jsonrpc"] == "2.0" and ("result" in msg or "error" in msg or "method" in msg)


def test_missing_store_exits_2(tmp_path):
    r = subprocess.run([sys.executable, "-m", "patch_precedent.cli", "mcp", "--store",
                        str(tmp_path / "nope.rl")], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=TIMEOUT)
    assert r.returncode == 2 and r.stdout == ""
    assert r.stderr.strip().count("\n") == 0 and "store not found" in r.stderr


def test_demo_and_explain_do_not_import_mcp(tmp_path):
    patch = pins.project_root() / "fixtures" / "release" / "docs-only.patch"
    code = (
        "import sys\n"
        "from patch_precedent.cli import main\n"
        f"rc = main(['explain', {str(patch)!r}])\n"
        "print('MCP', any(m == 'mcp' or m.startswith('mcp.') for m in sys.modules))\n"
        "sys.exit(rc)\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       timeout=TIMEOUT)
    assert r.returncode == 0, r.stderr
    assert "MCP False" in r.stdout
