import ast
from pathlib import Path

import pytest

from awl import core
from awl.core import (
    find_public_names,
    parse_control_flags,
    update_dunder_all,
)
from awl.core import (
    main as core_main,
)


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
    updated = update_dunder_all(file, ["bar"])
    content = file.read_text()
    assert updated is True
    assert '__all__ = ["bar"]' in content


def test_update_dunder_all_noop(tmp_path):
    file = tmp_path / "__init__.py"
    file.write_text('from .foo import bar\n__all__ = ["bar"]\n')
    updated = update_dunder_all(file, ["bar"])
    assert updated is False


def test_update_dunder_all_update(tmp_path):
    file = tmp_path / "__init__.py"
    file.write_text("from .foo import bar\n__all__ = []\n")
    updated = update_dunder_all(file, ["bar"])
    assert updated is True
    assert '__all__ = ["bar"]' in file.read_text()


def test_get_src_dirs(tmp_path):
    # Create a pyproject.toml with include patterns
    proj = tmp_path / "pyproject.toml"
    proj.write_text('[tool.hatch.build]\nincludes = ["src/pkg1/**", "src/pkg2/sub/**"]\n')
    dirs = core.get_src_dirs(proj)
    assert Path("src/pkg1") in dirs
    assert Path("src/pkg2/sub") in dirs


def test_core_main_no_pyproject(monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    # Ensure no pyproject.toml
    if (tmp_path / "pyproject.toml").exists():
        (tmp_path / "pyproject.toml").unlink()
    ret = core.main(None)
    out, _err = capsys.readouterr()
    assert ret is None
    assert "Error: no path given and no pyproject.toml found." in out


def test_core_main_single_file(tmp_path):
    # Create a simple package
    test_file = tmp_path / "__init__.py"
    test_file.write_text("from .foo import bar\n")
    core.main(str(test_file))
    content = test_file.read_text()
    assert '__all__ = ["bar"]' in content


def test_core_main_batch(tmp_path, monkeypatch):
    # Setup project structure
    (tmp_path / "src" / "mypkg").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[tool.hatch.build]\nincludes = ["src/mypkg/**"]\n')
    init = tmp_path / "src" / "mypkg" / "__init__.py"
    init.write_text("from .mod import val\n")
    (tmp_path / "src" / "mypkg" / "mod.py").write_text("val = 123\n")

    monkeypatch.chdir(tmp_path)
    core.main(None)
    # Should add __all__ to init
    content = init.read_text()
    assert '__all__ = ["val"]' in content


def test_update_dunder_all_dry_run(tmp_path, capsys):
    # Setup a simple __init__.py
    file = tmp_path / "__init__.py"
    file.write_text("from .foo import bar\n__all__ = []\n")
    # Dry run: no file write
    updated = update_dunder_all(file, ["bar"], dry_run=True, show_diff=False)
    assert updated is True
    # File should be unchanged on disk
    content = file.read_text()
    assert "__all__ = []" in content
    # And we should see the "Dry run" notice
    out, _ = capsys.readouterr()
    assert "📝 Dry run: no changes written" in out


def test_update_dunder_all_show_diff(tmp_path, capsys):
    # Setup a simple __init__.py without any __all__
    file = tmp_path / "__init__.py"
    file.write_text("from .foo import bar\n")
    # Show diff and actually write
    updated = update_dunder_all(file, ["bar"], dry_run=False, show_diff=True)
    assert updated is True
    # File should now contain __all__
    content = file.read_text()
    assert '__all__ = ["bar"]' in content
    # And the diff header should be in stdout
    out, _ = capsys.readouterr()
    assert out.startswith(f"--- {file}")
    assert '+__all__ = ["bar"]' in out


def test_update_dunder_all_multiple_assign(tmp_path, capsys):
    file = tmp_path / "__init__.py"
    # Two __all__ directives
    file.write_text("from .foo import bar\n__all__ = []\n__all__ = ['baz']\n")
    changed = update_dunder_all(file, ["bar"])
    assert changed is False
    out, _ = capsys.readouterr()
    assert "Multiple __all__ assignments" in out


def test_core_main_wildcard(tmp_path, capsys):
    f = tmp_path / "__init__.py"
    f.write_text("from .foo import *\n")
    core.main(str(f))
    out, _ = capsys.readouterr()
    assert "Wildcard import" in out
    assert "__all__" not in f.read_text()


def test_core_main_ignore_directive(tmp_path, capsys):
    f = tmp_path / "__init__.py"
    f.write_text("# awl:ignore\nfrom .foo import bar\n")
    core.main(str(f))
    out, _ = capsys.readouterr()
    assert "Skipped" in out
    assert "__all__" not in f.read_text()


def test_find_public_names_private_dropped():
    code = "from .foo import _hidden"
    flags = parse_control_flags(code)
    names = find_public_names(__import__("ast").parse(code), flags)
    assert names == []


def test_core_wildcard_skip(tmp_path, capsys):
    file = tmp_path / "__init__.py"
    file.write_text("from .foo import *\n")
    core_main(str(file))
    out, _ = capsys.readouterr()
    assert "Wildcard import" in out
    assert "__all__" not in file.read_text()


def test_core_ignore_directive(tmp_path, capsys):
    file = tmp_path / "__init__.py"
    file.write_text("# awl:ignore\nfrom .foo import bar\n")
    core_main(str(file))
    out, _ = capsys.readouterr()
    assert "Skipped" in out
    assert "__all__" not in file.read_text()
