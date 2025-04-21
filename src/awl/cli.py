from __future__ import annotations

import argparse
import atexit
import importlib.metadata
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import awl

if TYPE_CHECKING:
    from collections.abc import Generator


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


def get_tempfile() -> Path:
    """Create a temporary file and set up cleanup."""
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.close()
    temp_path = Path(temp_file.name).resolve()
    atexit.register(lambda: temp_path.unlink(missing_ok=True))
    return temp_path


def read_stdin(fmt: type[str | bytes] = str, chunk_size: int = 8192) -> Generator[str | bytes]:
    """Read stdin in chunks yield them."""
    while True:
        if fmt is str:
            chunk = sys.stdin.read(chunk_size)
        elif fmt is bytes:
            chunk = sys.stdin.buffer.read(chunk_size)
        if not chunk:
            break
        yield chunk


def read_stdin_to_tempfile(fmt: type[str | bytes] = str, chunk_size: int = 8192) -> Path:
    """Read stdin in chunks and write to a temporary file."""
    temp_path = get_tempfile()
    with temp_path.open("wb") as f:
        for chunk in read_stdin(fmt, chunk_size):
            f.write(chunk)
    return temp_path


def main() -> int:
    meta = get_metadata()
    arg_parser = argparse.ArgumentParser(
        prog=meta["name"],
        description=meta["description"],
    )

    # Positional arguments
    _ = arg_parser.add_argument("pos_name", type=str, nargs="?", default="")
    _ = arg_parser.add_argument("pos_input", nargs="?", help="Path to input file or '-' for stdin")

    # Optional flags
    _ = arg_parser.add_argument("-n", "--name", type=str, help="Name of person to greet.")
    _ = arg_parser.add_argument("-i", "--input", type=str, help="Path to input file or '-' for stdin")
    _ = arg_parser.add_argument(
        "-v", "--version", action="version", version=f"{meta['name']} version {meta['version']}"
    )

    args: argparse.Namespace = arg_parser.parse_args()

    # Disambiguation logic for name
    if args.name and args.pos_name and args.name != args.pos_name:
        print("Warning: both name flag and positional input provided; using --name/-n", file=sys.stderr)

    # input logic
    if args.input and args.pos_input and args.input != args.pos_input:
        print("Warning: both input flag and positional input provided; using --input/-i", file=sys.stderr)
    if not (input_loc := args.input or args.pos_input):
        arg_parser.error("Missing input file. Provide one using --input/-i or as a positional argument.")
    input_from_stdin = input_loc in {"-", None}

    if input_from_stdin:
        input_path = read_stdin_to_tempfile()  # function requires a path
    else:
        input_path = Path(input_loc).resolve()
        if not input_path.exists():
            print(f"Error: Input file does not exist: {input_path}", file=sys.stderr)
            return 1

    value = awl.main(input_path)
    print(value)

    return 0
