import importlib.metadata
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import awl.cli as awl_cli
from awl import cli

# Helpers
PYTHON = Path(sys.executable).resolve()
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"


def make_temp_project(structure: dict[str, str]) -> Path:
    base = Path(tempfile.mkdtemp())
    for rel, content in structure.items():
        path = base / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return base


def run_awl(args, cwd):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR)
    return subprocess.run(
        [PYTHON, "-m", "awl", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


# --- CLI Tests ---


def test_cli_single_file(tmp_path):
    pkg = tmp_path / "src" / "mypkg"
    pkg.mkdir(parents=True)
    init = pkg / "__init__.py"
    init.write_text("from .foo import bar\n")
    (pkg / "foo.py").write_text("bar = 42\n")

    result = run_awl([str(init)], cwd=tmp_path)
    assert result.returncode == 0
    assert '__all__ = ["bar"]' in init.read_text()
    assert not result.stderr


def test_cli_batch_from_pyproject():
    project = make_temp_project({
        "pyproject.toml": """
[tool.hatch.build]
includes = [\"src/mypkg/**\"]
""",
        "src/mypkg/__init__.py": "from .foo import bar\n",
        "src/mypkg/foo.py": "bar = 1\n",
    })
    result = run_awl([], cwd=project)
    assert result.returncode == 0
    code = (project / "src" / "mypkg" / "__init__.py").read_text()
    assert '__all__ = ["bar"]' in code


def test_cli_warn_conflicting_args(tmp_path):
    pkg = tmp_path / "src" / "mypkg"
    pkg.mkdir(parents=True)
    init = pkg / "__init__.py"
    init.write_text("from .foo import bar\n")
    (pkg / "foo.py").write_text("bar = 101\n")

    result = run_awl(["-i", str(init), str(init)], cwd=tmp_path)
    assert result.returncode == 0
    assert "using --input/-i" in result.stderr


def test_cli_read_stdin_and_write_stdout(tmp_path):
    pkg = tmp_path / "dummy"
    pkg.mkdir()
    foo = pkg / "foo.py"
    foo.write_text("bar = 7\n")

    p = subprocess.Popen(
        [PYTHON, "-m", "awl", "-i", "-"],
        cwd=tmp_path,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, "PYTHONPATH": str(SRC_DIR)},
    )
    stdin_content = "from .dummy.foo import bar\n"
    out, err = p.communicate(stdin_content)
    assert p.returncode == 0
    assert '__all__ = ["bar"]' in out
    assert not err


def test_read_stdin_chunks(monkeypatch):
    data = "hello world"
    monkeypatch.setattr(sys, "stdin", io.StringIO(data))
    chunks = list(cli.read_stdin(fmt=str, chunk_size=5))
    assert "".join(chunks) == data


def test_read_stdin_to_tempfile(monkeypatch):
    data = "abcde12345"
    monkeypatch.setattr(sys, "stdin", io.StringIO(data))
    temp = cli.read_stdin_to_tempfile(fmt=str, chunk_size=4)
    assert temp.read_text() == data


def test_get_metadata_package_not_found(monkeypatch):
    orig = importlib.metadata.version
    monkeypatch.setattr(
        importlib.metadata,
        "version",
        lambda name: (_ for _ in ()).throw(importlib.metadata.PackageNotFoundError(name)),
    )
    version_file = Path(cli.__file__).parent / "__version__.py"
    backup = version_file.read_text()
    version_file.write_text('__version__ = "9.9.9"')

    md = cli.get_metadata()
    assert md["version"] == "9.9.9"

    version_file.write_text(backup)
    monkeypatch.setattr(importlib.metadata, "version", orig)


def test_cli_main_batch(monkeypatch):
    called = []
    monkeypatch.setattr(
        awl_cli,
        "awl_main",
        lambda path=None, **_ignored: called.append(path),
    )
    monkeypatch.setattr(sys, "argv", ["awl"])
    ret = cli.main()
    assert ret == 0
    assert called == [None]


def test_cli_main_missing(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["awl", "nope.py"])
    ret = cli.main()
    _out, err = capsys.readouterr()
    assert ret == 1
    assert "Error: Input file does not exist" in err


def test_cli_dry_run_and_diff(tmp_path):
    pkg = tmp_path / "src" / "mypkg"
    pkg.mkdir(parents=True)
    init = pkg / "__init__.py"
    init.write_text("from .foo import bar\n__all__ = []\n")
    (pkg / "foo.py").write_text("bar = 3\n")

    result = run_awl(["--dry-run", str(init)], cwd=tmp_path)
    assert result.returncode == 0
    assert "📝 Dry run" in result.stdout
    assert "__all__ = []" in init.read_text()

    result = run_awl(["--diff", str(init)], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout.startswith(f"--- {init}")
    assert '__all__ = ["bar"]' in init.read_text()
