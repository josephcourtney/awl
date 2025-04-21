import re
import shutil
import subprocess

import pytest

import awl
import awl.cli


def test_get_metadata():
    meta = awl.cli.get_metadata()
    assert "_" not in meta["name"], "package names should contain dashes, not underscores"
    assert len(meta["description"]) > 0, "add a package description."

    semver_pattern = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"  # noqa: E501
    assert re.match(semver_pattern, meta["version"]) is not None, "use a semantic version format"


@pytest.mark.parametrize(
    ("args", "expected_output"),
    [
        (["--version"], f"awl version {awl.__version__}"),
        (["--help"], "usage:"),
    ],
)
def test_cli_args(args: list[str], expected_output: str) -> None:
    python_path = shutil.which("python")
    result = subprocess.run(
        [str(python_path), "-m", "awl", *args], capture_output=True, text=True, check=False
    )
    assert expected_output in result.stdout
    assert result.returncode == 0
    assert not result.stderr
