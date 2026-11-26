"""Stdio MCP server exposing one read-only tool: precedent_for_patch.

stdout carries protocol messages only. Nothing here prints; logging goes to stderr.
"""
import json
import logging
import sys
from pathlib import Path
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import WithJsonSchema
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from .diffparse import changed_files_from_text
from .evidence import precedent_for_patch

INSTRUCTIONS = ("Call precedent_for_patch with the full unified diff to get the decisions, "
                "checks and observed replay results behind the changed files.")
DESCRIPTION = (
    "Given a unified diff against relatedb/relate at the pinned commit, returns the "
    "architectural decisions (ADRs) governing each changed file, their rules and reasons, "
    "the regression checks that guard them, and each check's observed result from Patch "
    "Precedent's replay of this exact patch. Read-only.")
EMPTY_DIFF = "diff must be a non-empty unified diff"
NO_HEADERS = 'no "diff --git a/... b/..." file headers found; pass the full unified diff'


def _error(message: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=message)], is_error=True)


def build_server(store: Path, runs_root: Path) -> MCPServer:
    server = MCPServer("patch-precedent", instructions=INSTRUCTIONS, log_level="WARNING")

    @server.tool(
        name="precedent_for_patch", description=DESCRIPTION,
        annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False),
        structured_output=False)
    def precedent_tool(
            diff: Annotated[object, WithJsonSchema({"type": "string",
                            "description": "The full unified diff (git diff / patch text)."})]) -> CallToolResult:
        if not isinstance(diff, str) or not diff.strip():
            return _error(EMPTY_DIFF)
        try:
            if not changed_files_from_text(diff):
                return _error(NO_HEADERS)
            result = precedent_for_patch(diff, store, runs_root)
            text = json.dumps(result, indent=2, ensure_ascii=False)
        except Exception as exc:  # one clean line for the agent, never a traceback
            message = " ".join(f"{type(exc).__name__}: {exc}".split())
            return _error(message)
        return CallToolResult(content=[TextContent(type="text", text=text)])

    return server


def serve(store: Path, runs_root: Path) -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING, force=True)
    build_server(Path(store), Path(runs_root)).run("stdio")
