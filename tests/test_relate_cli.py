import hashlib
import json
import shutil
import subprocess

import pytest

from patch_precedent import pins, relate_cli
from patch_precedent.relate_cli import RelateCliError, ensure_relate_cli, relate_mcp_config


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("PATCH_PRECEDENT_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(relate_cli, "_supported_platform", lambda: True)
    return tmp_path / "cache"


def _target(cache):
    return cache / "relate-cli-1.3.0" / "relate-darwin-arm64"


def test_checksum_mismatch_deletes(cache):
    def fetch(url, dest):
        assert url.startswith("https://github.com/relatedb/relate/releases/download/v1.3.0/")
        dest.write_bytes(b"not the real binary")

    with pytest.raises(RelateCliError, match="sha256"):
        ensure_relate_cli(fetch=fetch)
    assert not _target(cache).exists()
    assert list(_target(cache).parent.glob("*")) == []  # no temp file left behind


def test_download_verifies_chmods_and_is_noop_when_present(cache, monkeypatch):
    blob = b"fake relate binary"
    monkeypatch.setattr(relate_cli, "SHA256", hashlib.sha256(blob).hexdigest())
    calls = []

    def fetch(url, dest):
        calls.append(url)
        dest.write_bytes(blob)

    path = ensure_relate_cli(fetch=fetch)
    assert path == _target(cache) and path.read_bytes() == blob
    assert path.stat().st_mode & 0o777 == 0o755
    assert ensure_relate_cli(fetch=fetch) == path
    assert len(calls) == 1  # verified file present: no second download


def test_unsupported_platform(cache, monkeypatch):
    monkeypatch.setattr(relate_cli, "_supported_platform", lambda: False)
    with pytest.raises(RelateCliError, match="relate CLI fetch supports macOS arm64 only"):
        ensure_relate_cli(fetch=lambda u, d: pytest.fail("must not download"))


def test_relate_mcp_config_shape(tmp_path):
    cli = tmp_path / "relate"
    cfg = relate_mcp_config(tmp_path / "copy.rl", cli=cli)
    assert cfg == {"mcpServers": {"relate": {"command": str(cli), "args": [
        "serve", "--mcp", "stdio", "--read-only", "--database", str(tmp_path / "copy.rl")]}}}


@pytest.mark.upstream
def test_relate_mcp_reads_store(tmp_path):
    cli = ensure_relate_cli()
    store = tmp_path / "copy.rl"
    shutil.copy2(pins.STORE_PATH, store)
    before = store.read_bytes()
    spec = relate_mcp_config(store, cli=cli)["mcpServers"]["relate"]
    proc = subprocess.Popen([spec["command"], *spec["args"]], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    n = 0

    def rpc(method, params=None, notify=False):
        nonlocal n
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            n += 1
            msg["id"] = n
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        while not notify:
            r = json.loads(proc.stdout.readline())
            if r.get("id") == n:
                return r["result"]

    try:
        rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "pytest", "version": "0"}})
        rpc("notifications/initialized", notify=True)
        tools = rpc("tools/list")["tools"]
        assert sorted(t["name"] for t in tools) == ["get_schema", "read_cypher"]
        res = rpc("tools/call", {"name": "read_cypher", "arguments": {
            "statement": "MATCH (f:File {path: $p})-[:CITES]->(d:Decision) RETURN DISTINCT d.id AS id",
            "parameters": {"p": "distribution/install.sh"}}})
        text = json.dumps(res)
        import re
        assert len(set(re.findall(r"ADR-\d+", text))) == 6 and "ADR-0585" in text
    finally:
        proc.stdin.close()
        proc.wait(timeout=20)
    assert store.read_bytes() == before
