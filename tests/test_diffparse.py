import hashlib
import shutil

import pytest

from patch_precedent.diffparse import read_patch
from patch_precedent.pins import project_root

FIX = project_root() / "fixtures" / "installer"


@pytest.mark.parametrize("name", ["wording.patch", "release-lookup.patch", "token-header.patch"])
def test_read_patch_changed_files(name):
    info = read_patch(FIX / name)
    assert info.changed_files == ("distribution/install.sh",)
    assert info.path == FIX / name
    assert info.label == name.removesuffix(".patch")


def test_patch_id_follows_content(tmp_path):
    copy = tmp_path / "renamed.patch"
    shutil.copyfile(FIX / "wording.patch", copy)
    a, b = read_patch(FIX / "wording.patch"), read_patch(copy)
    assert a.id == b.id == "patch:" + a.sha256[:12]
    assert a.sha256 == b.sha256
    assert a.label != b.label


def test_sha256_hashes_raw_bytes(tmp_path):
    p = tmp_path / "crlf.patch"
    raw = b"diff --git a/x b/x\r\n--- a/x\r\n+++ b/x\r\n@@ -1 +1 @@\r\n-a\t\r\n+b\r\n"
    p.write_bytes(raw)
    assert read_patch(p).sha256 == hashlib.sha256(raw).hexdigest()


def test_no_diff_header_gives_empty(tmp_path):
    p = tmp_path / "empty.patch"
    p.write_text("not a diff\n")
    assert read_patch(p).changed_files == ()


def test_b_side_dev_null_uses_a_side_and_dedupes(tmp_path):
    p = tmp_path / "multi.patch"
    p.write_text(
        "diff --git a/old.txt b/old.txt\n"
        "diff --git a/gone.txt /dev/null\n"
        "diff --git a/old.txt b/old.txt\n"
        "diff --git a/new.txt b/new.txt\n"
    )
    assert read_patch(p).changed_files == ("old.txt", "gone.txt", "new.txt")
