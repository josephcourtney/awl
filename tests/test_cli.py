import re

from click.testing import CliRunner

import awl
from awl.cli import main as cli_main


def strip_ansi(text):
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_cli_shows_help():
    runner = CliRunner()
    result = runner.invoke(cli_main, ["--help"])
    assert result.exit_code == 0
    assert "Awl — keep __all__ declarations in sync with imports." in result.output


def test_cli_shows_version():
    runner = CliRunner()
    result = runner.invoke(cli_main, ["--version"])
    assert result.exit_code == 0
    assert "awl, version" in result.output


def test_cli_no_pyproject(tmp_path, monkeypatch, patch_console):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli_main, [])
    output = patch_console.getvalue()

    assert result.exit_code == 1
    assert "No pyproject.toml found" in output


def test_cli_single_file_basic(tmp_path):
    init_file = tmp_path / "__init__.py"
    init_file.write_text("from .foo import bar\n")
    runner = CliRunner()
    result = runner.invoke(cli_main, [str(init_file)])
    assert result.exit_code == 0
    assert '__all__ = ["bar"]' in init_file.read_text()


def test_cli_dry_run(tmp_path, patch_console):
    init_file = tmp_path / "__init__.py"
    init_file.write_text("from .foo import bar\n")
    runner = CliRunner()
    result = runner.invoke(cli_main, ["--dry-run", str(init_file)])
    output = patch_console.getvalue()

    assert result.exit_code == 0
    assert "Dry run: would update" in output
    assert '__all__ = ["bar"]' not in init_file.read_text()  # unchanged due to dry run


def test_cli_verbose_output(tmp_path, patch_console):
    init_file = tmp_path / "__init__.py"
    init_file.write_text("from .foo import bar\n")
    runner = CliRunner()
    result = runner.invoke(cli_main, ["--verbose", str(init_file)])
    output = patch_console.getvalue()

    assert result.exit_code == 0
    assert "Old __all__" in output
    assert "New __all__" in output


def test_cli_ignore_directive(tmp_path, patch_console):
    init_file = tmp_path / "__init__.py"
    init_file.write_text("# awl:ignore\nfrom .foo import bar\n")
    runner = CliRunner()
    result = runner.invoke(cli_main, [str(init_file)])
    output = patch_console.getvalue()
    assert result.exit_code == 0
    assert "Skipped" in output


def test_cli_stdin(patch_console):
    code = "from .foo import bar\n"
    runner = CliRunner()
    result = runner.invoke(cli_main, ["-i", "-", "-v"], input=code)
    output = patch_console.getvalue()

    assert result.exit_code == 0
    assert "bar" in output
    assert "New __all__" in output


def test_cli_input_file_not_found(tmp_path, patch_console):
    missing_file = tmp_path / "does_not_exist.py"
    runner = CliRunner()
    result = runner.invoke(cli_main, ["-i", str(missing_file)])
    output = patch_console.getvalue()

    assert result.exit_code == 1
    assert "Error: Input file does not exist" in output


def test_cli_warns_on_conflicting_input_sources(tmp_path, patch_console):
    file = tmp_path / "__init__.py"
    file.write_text("from .foo import bar\n")
    runner = CliRunner()
    result = runner.invoke(cli_main, [str(file), "-i", str(file)])
    output = patch_console.getvalue()

    assert "both input flag and positional input provided" in output
    assert result.exit_code == 0


def test_cli_dry_run_verbose(tmp_path, patch_console):
    file = tmp_path / "__init__.py"
    file.write_text("from .foo import bar\n")
    runner = CliRunner()
    result = runner.invoke(cli_main, [str(file), "-v", "-d"])
    output = patch_console.getvalue()

    assert result.exit_code == 0
    assert "Old __all__" in output
    assert "New __all__" in output
    assert "Dry run: would update" in output


def test_cli_stdin_print_error(monkeypatch, patch_console):
    # Force the function that reads the temp file to raise OSError
    def fake_print_stdin_contents(_path):
        msg = "broken file"
        raise OSError(msg)

    monkeypatch.setattr(awl.cli, "_print_stdin_contents", fake_print_stdin_contents)

    runner = CliRunner()
    result = runner.invoke(cli_main, ["-i", "-", "-v"], input="from .foo import bar\n")

    output = strip_ansi(patch_console.getvalue())
    assert result.exit_code == 1
    assert "Error reading temporary file: broken file" in output


def test_cli_invalid_pyproject(monkeypatch, tmp_path, patch_console):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("not really a toml file")
    monkeypatch.chdir(tmp_path)

    # Prevent version lookup from crashing
    monkeypatch.setattr("importlib.metadata.version", lambda name: "0.1.0")

    runner = CliRunner()
    result = runner.invoke(cli_main, ["--version"])

    assert result.exit_code == 0

    output = strip_ansi(patch_console.getvalue())
    assert "Could not read project metadata" in output
