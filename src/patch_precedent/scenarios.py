"""Scenario registry: which harness to run, with which fixtures and expectations."""
from dataclasses import dataclass
from pathlib import Path

from . import pins


@dataclass(frozen=True)
class Scenario:
    name: str
    harness_cmd: tuple[str, ...]
    fixtures_dir: Path
    expectations_path: Path
    timeout_s: int


def _scenario(name: str, harness_cmd: tuple[str, ...]) -> Scenario:
    fixtures = pins.project_root() / "fixtures" / name
    return Scenario(name, harness_cmd, fixtures, fixtures / "expectations.toml",
                    pins.HARNESS_TIMEOUT_S)


SCENARIOS: dict[str, Scenario] = {
    s.name: s
    for s in (
        _scenario("installer", pins.HARNESS_CMD),
        _scenario("release", ("sh", "scripts/tests/test_release_advance.sh")),
    )
}


def get_scenario(name: str) -> Scenario:
    try:
        return SCENARIOS[name]
    except KeyError:
        raise KeyError(f"unknown scenario {name!r} (available: {', '.join(SCENARIOS)})") from None
