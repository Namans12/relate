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


def _c1():
    return _text(FIX / "installer" / "release-lookup.patch")


def _changed_only(text):
    return "\n".join(l for l in text.splitlines()
                     if l.startswith(("diff --git", "+++ ", "--- ", "@@"))
                     or l[:1] in "+-") + "\n"


def test_key_ignores_context_trimming():
    text = _c1()
    key = patch_key(text)
    assert patch_key(_changed_only(text)) == key
    assert patch_key("\n".join(text.splitlines()[:-2]) + "\n") == key
    assert _changed_only(text) != text


def test_key_ignores_hunk_header_changes():
    text = _c1()
    import re
    shifted = re.sub(r"^@@ .* @@.*$", "@@ -1,1 +1,1 @@ foo", text, flags=re.M)
    assert shifted != text and patch_key(shifted) == patch_key(text)


def test_key_changes_when_a_changed_line_changes():
    text = _c1()
    line = next(l for l in text.splitlines() if l.startswith("+") and not l.startswith("+++")
                and l[1:].strip())
    assert patch_key(text.replace(line, line + "x", 1)) != patch_key(text)
    assert patch_key(text.replace(line, "-" + line[1:], 1)) != patch_key(text)


def test_key_per_file():
    a = "diff --git a/x b/x\n+hello\n"
    assert patch_key(a) != patch_key(a.replace("x b/x", "y b/y").replace("a/x", "a/y"))


def test_key_distinguishes_all_six_fixtures():
    test_key_distinguishes_patches()


def test_key_sensitive_to_content():
    assert patch_key("+a b\n") == patch_key("+ab\n")
    assert patch_key("+ab\n") != patch_key("+abc\n")


def test_changed_files_from_text_matches_and_handles_empty():
    assert changed_files_from_text(_text(FIX / "installer" / "wording.patch")) == (
        "distribution/install.sh",)
    assert changed_files_from_text("") == ()
    assert changed_files_from_text("not a diff\n") == ()
