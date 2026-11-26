import pytest

from patch_precedent.diffparse import changed_files_from_text
from patch_precedent.identity import patch_key
from patch_precedent.pins import project_root

FIX = project_root() / "fixtures"
ALL = sorted(FIX.glob("*/*.patch"))


def _text(p):
    return p.read_bytes().decode("utf-8")


def test_six_fixtures():
    assert len(ALL) == 6


@pytest.mark.parametrize("p", ALL, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_key_ignores_whitespace_mangling(p):
    text = _text(p)
    key = patch_key(text)
    assert key.startswith("pk:") and len(key) == 3 + 16
    assert patch_key(text.replace("\n", "\r\n")) == key
    assert patch_key(text.replace("\n", "  \n")) == key
    assert patch_key(text.replace("\t", "    ")) == key
    assert patch_key("\n\n" + text + "\n\n") == key


def test_key_distinguishes_patches():
    keys = [patch_key(_text(p)) for p in ALL]
    assert len(set(keys)) == len(keys)


def test_key_sensitive_to_content():
    assert patch_key("+a b\n") == patch_key("+ab\n")
    assert patch_key("+ab\n") != patch_key("+abc\n")


def test_changed_files_from_text_matches_and_handles_empty():
    assert changed_files_from_text(_text(FIX / "installer" / "wording.patch")) == (
        "distribution/install.sh",)
    assert changed_files_from_text("") == ()
    assert changed_files_from_text("not a diff\n") == ()
