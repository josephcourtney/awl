from __future__ import annotations

import argparse
import atexit
import importlib.metadata
import logging
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

from awl.core import main as awl_main

if TYPE_CHECKING:
    from collections.abc import Generator

logger = logging.getLogger(__name__)


def get_metadata() -> dict[str, str]:
    """Retrieve CLI metadata, falling back if package metadata is missing."""
    pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
    description = "description unavailable."
    if pyproject_path.exists():
        try:
            with pyproject_path.open("rb") as f:
                data = tomllib.load(f)
            description = data.get("project", {}).get("description", description)
        except (OSError, tomllib.TOMLDecodeError):
            pass

    try:
        version = importlib.metadata.version("awl")
    except importlib.metadata.PackageNotFoundError:
        # Development mode; read from __version__.py
        version_file = Path(__file__).parent / "__version__.py"
        try:
            text = version_file.read_text()
            version = text.split("=", 1)[1].strip().strip('"')
        except (OSError, IndexError, ValueError):
            version = "0.0.0"

    return {"name": "awl", "description": description, "version": version}


def get_tempfile() -> Path:
    """Create a temporary file and register it for cleanup."""
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_path = Path(temp_file.name).resolve()
    atexit.register(lambda: temp_path.unlink(missing_ok=True))
    return temp_path


def read_stdin(fmt: type[str | bytes] = str, chunk_size: int = 8192) -> Generator[str | bytes]:
    """Read stdin in chunks and yield them."""
    while True:
        chunk = sys.stdin.read(chunk_size) if fmt is str else sys.stdin.buffer.read(chunk_size)
        if not chunk:
            break
        yield chunk


def read_stdin_to_tempfile(fmt: type[str | bytes] = str, chunk_size: int = 8192) -> Path:
    """Read stdin in chunks and write to a temporary file."""
    temp_path = get_tempfile()
    with temp_path.open("wb") as f:
        for data in read_stdin(fmt, chunk_size):
            bytes_chunk = data.encode() if isinstance(data, str) else data
            f.write(bytes_chunk)
    return temp_path


def main() -> int:
    meta = get_metadata()
    parser = argparse.ArgumentParser(
        prog=meta["name"],
        description=meta["description"],
    )

    # quiet/verbose flags
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Only show warnings and errors, suppress informational messages.",
    )
    parser.add_argument(
        "-V", "--verbose", action="store_true", help="Show debug-level output for troubleshooting."
    )

    parser.add_argument(
        "pos_input",
        nargs="?",
        help="Path to input file or '-' for stdin",
    )
    parser.add_argument(
        "-i",
        "--input",
        help="Path to input file or '-' for stdin",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change, but do not write any files.",
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Print a unified diff of any changes (works with or without --dry-run).",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"{meta['name']} version {meta['version']}",
    )

    args = parser.parse_args()

    # configure logging
    if args.quiet:
        level = logging.WARNING
    elif args.verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(level=level, format="%(message)s")

    logger.debug("CLI args: %s", args)

    # Batch/discovery mode
    if not args.input and not args.pos_input:
        awl_main(None, dry_run=args.dry_run, show_diff=args.diff)
        return 0

    # Warn if both provided
    if args.input and args.pos_input:
        print(
            "Warning: both input flag and positional input provided; using --input/-i",
            file=sys.stderr,
        )

    input_loc = args.input or args.pos_input
    stdin_mode = input_loc == "-"

    if stdin_mode:
        input_path = read_stdin_to_tempfile()
    else:
        input_path = Path(input_loc).resolve()
        if not input_path.exists():
            print(f"Error: Input file does not exist: {input_path}", file=sys.stderr)
            return 1

    awl_main(str(input_path), dry_run=args.dry_run, show_diff=args.diff)

    if stdin_mode:
        try:
            new_code = input_path.read_text()
            sys.stdout.write(new_code)
        except OSError as e:
            print("Error reading temporary file:", e, file=sys.stderr)
            return 1

    return 0
