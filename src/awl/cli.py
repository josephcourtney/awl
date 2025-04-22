import atexit
import importlib
import logging
import sys
import tempfile
import tomllib
from collections.abc import Generator
from pathlib import Path

import click

from awl.core import main as awl_main

from .__version__ import __version__


def get_metadata() -> dict[str, str]:
    pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
    description: str = "description unavailable."
    if pyproject_path.exists():
        with pyproject_path.open("rb") as f:
            data = tomllib.load(f)
        description = data["project"]["description"]
    version = importlib.metadata.version("awl")
    return {
        "name": "awl",
        "description": description,
        "version": version,
    }


def read_stdin(fmt: type[str | bytes] = str, chunk_size: int = 8192) -> Generator[str | bytes]:
    while True:
        chunk = sys.stdin.read(chunk_size) if fmt is str else sys.stdin.buffer.read(chunk_size)
        if not chunk:
            break
        yield chunk


def read_stdin_to_tempfile(fmt: type[str | bytes] = str, chunk_size: int = 8192) -> Path:
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_path = Path(temp_file.name).resolve()
    atexit.register(lambda: temp_path.unlink(missing_ok=True))

    with temp_path.open("wb") as f:
        for data in read_stdin(fmt, chunk_size):
            bytes_chunk = data.encode() if isinstance(data, str) else data
            f.write(bytes_chunk)
    return temp_path


logger = logging.getLogger(__name__)


@click.command(
    name="awl",
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Awl — keep __all__ declarations in sync with imports.",
)
@click.argument("pos_input", required=False)
@click.option(
    "-i", "--input", "input_path", type=click.Path(exists=False), help="Path to input file or '-' for stdin"
)
@click.option("-d", "--dry-run", is_flag=True, help="Show what would change, but do not write any files.")
@click.option("-v", "--verbose", is_flag=True, help="Show old and new __all__ values for all files.")
@click.option("-q", "--quiet", is_flag=True, help="Suppress non-critical output.")
@click.version_option(__version__, "-V", "--version", package_name="awl")
def main(pos_input, input_path, dry_run, verbose, quiet):
    """Awl — keep __all__ declarations in sync with imports."""
    # Setup logging
    level = logging.WARNING if quiet else (logging.DEBUG if verbose else logging.INFO)
    logging.basicConfig(level=level, format="%(message)s")

    # Determine input path
    input_path = input_path or pos_input
    if input_path and pos_input:
        click.echo("Warning: both input flag and positional input provided; using --input/-i", err=True)

    if not input_path:
        awl_main(None, dry_run=dry_run, verbose=verbose)
        return

    # Handle stdin
    if input_path == "-":
        input_path = read_stdin_to_tempfile(fmt=str)
    else:
        input_path = Path(input_path)
        if not input_path.exists():
            click.echo(f"Error: Input file does not exist: {input_path}", err=True)
            sys.exit(1)

    awl_main(str(input_path), dry_run=dry_run, verbose=verbose)

    if input_path == "-":
        try:
            click.echo(input_path.read_text())
        except OSError as e:
            click.echo(f"Error reading temporary file: {e}", err=True)
            sys.exit(1)
