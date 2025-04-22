import ast
from pathlib import Path

import pytest

from awl import core
from awl.core import (
    find_public_names,
    parse_control_flags,
    update_dunder_all,
)
from awl.core import main as core_main


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (
            "# awl:ignore\nfrom .foo import bar",
            {
                "file": {"ignore_file": True, "include_private": False, "exclude_public": False},
                "lines": {1: {"ignore"}},
            },
        ),
        (
            "# awl:include-private\nfrom .foo import _bar",
            {
                "file": {"ignore_file": False, "include_private": True, "exclude_public": False},
                "lines": {1: {"include_private"}},
            },
        ),
        (
            "from .foo import bar  # awl:exclude-public",
            {
                "file": {"ignore_file": False, "include_private": False, "exclude_public": True},
                "lines": {1: {"exclude_public"}},
            },
        ),
    ],
)
def test_parse_control_flags(code, expected):
    result = parse_control_flags(code)
    assert result == expected


def test_find_public_names_basic():
    code = """
from .foo import bar
from .baz import _qux  # awl:include-private
"""
    flags = parse_control_flags(code)
    tree = ast.parse(code)
    names = find_public_names(tree, flags)
    assert sorted(names) == ["_qux", "bar"]


def test_update_dunder_all_add(tmp_path):
    file = tmp_path / "__init__.py"
    file.write_text("from .foo import bar\n")
    changed, _reason = update_dunder_all(file, ["bar"])
    content = file.read_text()
    assert changed is True
    assert '__all__ = ["bar"]' in content


def test_update_dunder_all_noop(tmp_path):
    file = tmp_path / "__init__.py"
    file.write_text('from .foo import bar\n__all__ = ["bar"]\n')
    changed, _reason = update_dunder_all(file, ["bar"])
    assert changed is False


def test_update_dunder_all_update(tmp_path):
    file = tmp_path / "__init__.py"
    file.write_text("from .foo import bar\n__all__ = []\n")
    changed, _reason = update_dunder_all(file, ["bar"])
    assert changed is True
    assert '__all__ = ["bar"]' in file.read_text()


def test_get_src_dirs(tmp_path):
    proj = tmp_path / "pyproject.toml"
    proj.write_text('[tool.hatch.build]\nincludes = ["src/pkg1/**", "src/pkg2/sub/**"]\n')
    dirs = core.get_src_dirs(proj)
    assert Path("src/pkg1") in dirs
    assert Path("src/pkg2/sub") in dirs


def test_core_main_no_pyproject(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    pyproject = tmp_path / "pyproject.toml"
    if pyproject.exists():
        pyproject.unlink()
    results = core.main(None)
    assert isinstance(results, list)
    assert results[0]["status"] == "error"
    assert results[0]["reason"] == "no-pyproject"


def test_core_main_single_file(tmp_path):
    test_file = tmp_path / "__init__.py"
    test_file.write_text("from .foo import bar\n")
    results = core.main(str(test_file))
    content = test_file.read_text()
    assert '__all__ = ["bar"]' in content
    assert results[0]["status"] in {"changed", "unchanged"}


def test_core_main_batch(tmp_path, monkeypatch):
    (tmp_path / "src" / "mypkg").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[tool.hatch.build]\nincludes = ["src/mypkg/**"]\n')
    init = tmp_path / "src" / "mypkg" / "__init__.py"
    init.write_text("from .mod import val\n")
    (tmp_path / "src" / "mypkg" / "mod.py").write_text("val = 123\n")

    monkeypatch.chdir(tmp_path)
    results = core.main(None)
    assert '__all__ = ["val"]' in init.read_text()
    assert results[0]["status"] in {"changed", "unchanged"}


def test_update_dunder_all_dry_run(tmp_path):
    file = tmp_path / "__init__.py"
    file.write_text("from .foo import bar\n__all__ = []\n")
    changed, _reason = update_dunder_all(file, ["bar"], dry_run=True)
    assert changed is True
    content = file.read_text()
    assert "__all__ = []" in content


def test_update_dunder_all_multiple_assign(tmp_path):
    file = tmp_path / "__init__.py"
    file.write_text("from .foo import bar\n__all__ = []\n__all__ = ['baz']\n")
    changed, reason = update_dunder_all(file, ["bar"])
    assert changed is False
    assert reason == "Multiple __all__ assignments"


def test_core_main_wildcard(tmp_path):
    f = tmp_path / "__init__.py"
    f.write_text("from .foo import *\n")
    results = core.main(str(f))
    assert results[0]["status"] == "skip"
    assert results[0]["reason"] == "wildcard"


def test_core_main_ignore_directive(tmp_path):
    f = tmp_path / "__init__.py"
    f.write_text("# awl:ignore\nfrom .foo import bar\n")
    results = core.main(str(f))
    assert results[0]["status"] == "skip"
    assert results[0]["reason"] == "ignore"


def test_find_public_names_private_dropped():
    code = "from .foo import _hidden"
    flags = parse_control_flags(code)
    names = find_public_names(ast.parse(code), flags)
    assert names == []


def test_core_ignore_directive(tmp_path):
    file = tmp_path / "__init__.py"
    file.write_text("# awl:ignore\nfrom .foo import bar\n")
    results = core_main(str(file))
    assert results[0]["status"] == "skip"
    assert results[0]["reason"] == "ignore"


def test_extract_current_all_tuple(tmp_path):
    file = tmp_path / "__init__.py"
    file.write_text('from .foo import bar\n__all__ = ("bar", "_baz")\n')
    tree = ast.parse(file.read_text())
    result = core.extract_current_all(tree)
    assert result == ["bar", "_baz"]


def test_extract_current_all_malformed(tmp_path):
    file = tmp_path / "__init__.py"
    file.write_text("from .foo import bar\n__all__ = get_all()\n")
    tree = ast.parse(file.read_text())
    result = core.extract_current_all(tree)
    assert result is None


def test_format_new_block_multiline(tmp_path):
    long_names = [f"symbol_{i}" for i in range(20)]  # will force multiline
    file = tmp_path / "__init__.py"
    file.write_text("from .foo import " + ", ".join(long_names) + "\n")

    changed, _ = update_dunder_all(file, long_names)
    content = file.read_text()

    assert changed is True
    assert "[\n" in content  # multiline __all__
    assert all(f'"symbol_{i}",' in content for i in range(20))


def test_extract_current_all_raises():
    # Craft an invalid __all__ manually
    tree = ast.parse("__all__ = 123 + undefined\n")
    result = core.extract_current_all(tree)
    assert result is None


def test_find_public_names_excludes_all():
    code = """
from .foo import bar  # awl:exclude-public
from .foo import _baz
"""
    flags = parse_control_flags(code)
    tree = ast.parse(code)
    names = find_public_names(tree, flags)
    assert names == []
