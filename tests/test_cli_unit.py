from click.testing import CliRunner

from awl import cli


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli.main, ["--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output
    assert "awl" in result.output
    assert "--dry-run" in result.output
    assert "--verbose" in result.output


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli.main, ["--version"])
    assert result.exit_code == 0
    assert "awl, version" in result.output


def test_cli_warn_on_conflicting_inputs(tmp_path):
    test_file = tmp_path / "__init__.py"
    test_file.write_text("from .foo import bar\n")
    runner = CliRunner()
    result = runner.invoke(cli.main, [str(test_file), "-i", str(test_file)])
    assert result.exit_code == 0
    assert "using --input/-i" in result.output


def test_cli_verbose_output(tmp_path):
    init_file = tmp_path / "__init__.py"
    init_file.write_text("from .foo import bar\n")
    runner = CliRunner()
    result = runner.invoke(cli.main, [str(init_file), "--verbose"])
    assert result.exit_code == 0
    assert "Old __all__:" in result.output
    assert "New __all__:" in result.output


def test_cli_dry_run_adds_all(tmp_path):
    init_file = tmp_path / "__init__.py"
    init_file.write_text("from .foo import bar\n")
    runner = CliRunner()
    result = runner.invoke(cli.main, [str(init_file), "--dry-run"])
    assert result.exit_code == 0
    assert "📝 Dry run" in result.output
    assert '__all__ = ["bar"]' in result.output


def test_cli_diff_flag(tmp_path):
    init_file = tmp_path / "__init__.py"
    init_file.write_text("from .foo import bar\n__all__ = []\n")
    runner = CliRunner()
    result = runner.invoke(cli.main, [str(init_file), "--diff"])
    assert result.exit_code == 0
    assert result.output.startswith(f"--- {init_file}")
    assert '+__all__ = ["bar"]' in result.output
