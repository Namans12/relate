import hashlib

import pytest

from patch_precedent import pins
from patch_precedent.cli import main
from patch_precedent.pins import project_root

HASHES = {
    "wording.patch": "96278d65b413302fa666500df1941180248cf2e0eab8b3d5e67ace9bcc8cff29",
    "release-lookup.patch": "635b00b21f4b918ab73a400abdda636e8923d76b2ada61ccc2bc5d17dc0217e5",
    "token-header.patch": "5146b525a26dbcaf1cba5c3fa781d77a5ffd5085b1295a3c68faec6f565906ba",
}


@pytest.mark.parametrize("name", sorted(HASHES))
def test_fixture_hashes(name):
    data = (project_root() / "fixtures" / "installer" / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == HASHES[name]


def test_cli_help():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_project_root():
    assert (project_root() / "evidence").is_dir()
    assert (project_root() / "pyproject.toml").is_file()


def test_pins():
    assert pins.UPSTREAM_SHA == "5f7a510713c3feac146133e77d8c5bb72bae1b11"
    assert pins.IMPLEMENTING_SHA == "5ac38808547d11f55b02333624cc3e88b46566eb"
    assert pins.RELATE_VERSION == "1.1.0"
    assert pins.HARNESS_CMD == ("sh", "scripts/tests/test_install_sh.sh")
    assert pins.HARNESS_TIMEOUT_S == 600
    assert pins.STORE_PATH == project_root() / "data" / "precedent.rl"
