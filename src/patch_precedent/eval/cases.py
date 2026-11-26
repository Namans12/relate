"""The six evaluation cases and the single shared prompt template."""
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ..pins import project_root


@dataclass(frozen=True)
class Case:
    id: str
    scenario: str
    fixture: str  # repo-relative
    verdict: str
    decisions: tuple[str, ...]
    check_outcomes: dict[str, str]

    def diff_text(self) -> str:
        return (project_root() / self.fixture).read_bytes().decode("utf-8")


def cases_path() -> Path:
    return project_root() / "eval" / "cases.toml"


def prompt_path() -> Path:
    return project_root() / "eval" / "prompt.md"


def load_cases(path: Path | None = None) -> list[Case]:
    data = tomllib.loads((path or cases_path()).read_text(encoding="utf-8"))
    return [Case(c["id"], c["scenario"], c["fixture"], c["verdict"], tuple(c["decisions"]),
                 dict(c.get("check_outcomes", {}))) for c in data["cases"]]


def render_prompt(template: str, diff: str) -> str:
    """Plain replace, not .format: diffs contain braces. One trailing newline is dropped."""
    return template.replace("{patch}", diff.removesuffix("\n"))
