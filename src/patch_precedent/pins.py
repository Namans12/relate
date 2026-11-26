"""Pinned constants: upstream URL and SHAs, harness command, project root."""
import os
from pathlib import Path

UPSTREAM_URL = (
    os.environ.get("PATCH_PRECEDENT_UPSTREAM_URL")
    or "https://github.com/relatedb/relate.git"
)
UPSTREAM_SHA = "5f7a510713c3feac146133e77d8c5bb72bae1b11"
IMPLEMENTING_SHA = "5ac38808547d11f55b02333624cc3e88b46566eb"
RELATE_VERSION = "1.1.0"
HARNESS_CMD = ("sh", "scripts/tests/test_install_sh.sh")
HARNESS_TIMEOUT_S = 600


def project_root() -> Path:
    """First ancestor of this file containing both pyproject.toml and evidence/."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "evidence").is_dir():
            return parent
    raise RuntimeError(
        "patch-precedent project root not found: no ancestor of "
        f"{Path(__file__).resolve()} contains both pyproject.toml and evidence/"
    )


STORE_PATH = project_root() / "data" / "precedent.rl"
