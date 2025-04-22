import atexit
import importlib
import logging
import sys
import tempfile
import tomllib
from collections.abc import Generator
from pathlib import Path

import click
from rich.console import Console

from awl.core import main as core_main

from .__version__ import __version__

# Default console, patchable for tests
_default_console = Console()


def get_console() -> Console:
    return getattr(sys, "_awl_console", _default_console)


def get_metadata() -> dict[str, str]:
    pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
    description: str = "description unavailable."
    if pyproject_path.exists():
        try:
            with pyproject_path.open("rb") as f:
                data = tomllib.load(f)
            description = data["project"]["description"]

        except (tomllib.TOMLDecodeError, KeyError) as e:
            get_console().print(f"[yellow]⚠ Could not read project metadata: {e}[/yellow]")
    try:
        version = importlib.metadata.version("awl")
    except Exception:
        version = __version__
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


def _resolve_input_path(pos_input: str | Path, input_path: str | Path) -> Path | str | None:
    input_path = input_path or pos_input
    if input_path and pos_input:
        get_console().print(
            "[yellow]Warning: both input flag and positional input provided; using --input/-i[/yellow]"
        )

    if not input_path:
        return None

    if input_path == "-":
        return read_stdin_to_tempfile(fmt=str)

    path = Path(input_path)
    if not path.exists():
        get_console().print(f"[red]Error: Input file does not exist: {path}[/red]")
        sys.exit(1)

    return path


def _run_awl(
    input_path: str | None,
    *,
    dry_run: bool,
    verbose: bool,
) -> list[dict]:
    return core_main(str(input_path) if input_path else None, dry_run=dry_run, verbose=verbose)


def _render_results(result, verbose, dry_run):
    for entry in result:
        status = entry.get("status")
        file_path = entry.get("file")

        if status == "error" and entry.get("reason") == "no-pyproject":
            get_console().print("[red]❌ No pyproject.toml found and no path was given.[/red]")
            sys.exit(1)

        if status == "skip":
            reason = entry.get("reason")
            if reason == "wildcard":
                get_console().print(f"[yellow]⚠ Skipped {file_path} due to wildcard import.[/yellow]")
            elif reason == "ignore":
                get_console().print(f"[cyan]⏭ Skipped {file_path} (marked with # awl:ignore)[/cyan]")
            continue

        if verbose:
            get_console().rule(f"[bold]{file_path}[/bold]")
            old_all = entry.get("old_all")
            new_all = entry.get("new_all")
            get_console().print(f"[dim]Old __all__:[/dim] {old_all}")
            get_console().print(f"[green]New __all__:[/green] {new_all}")

        if entry.get("reason") == "Multiple __all__ assignments":
            get_console().print(f"[yellow]⚠ Multiple __all__ assignments in {file_path}; skipping.[/yellow]")

        if status == "unchanged":
            get_console().print(f"[green]✓ {file_path} — up to date[/green]")
        elif status == "changed":
            msg = "📝 Dry run: would update" if dry_run else "🔁 Updated __all__ in"
            get_console().print(f"[blue]{msg} {file_path}[/blue]")


def _print_stdin_contents(input_path):
    if isinstance(input_path, Path):
        try:
            get_console().print(input_path.read_text(encoding="utf-8"))
        except OSError as e:
            get_console().print(f"[red]Error reading temporary file: {e}[/red]")
            sys.exit(1)


def _print_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    meta = get_metadata()
    name = meta.get("name", "awl")
    version = meta.get("version", __version__)
    click.echo(f"{name}, version {version}")
    ctx.exit()


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
@click.option(
    "-V",
    "--version",
    "version_flag",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_print_version,
    help="Show version and exit",
)
def main(pos_input, input_path, dry_run, verbose, quiet):
    """Awl — keep __all__ declarations in sync with imports."""
    level = logging.WARNING if quiet else (logging.DEBUG if verbose else logging.INFO)
    logging.basicConfig(level=level, format="%(message)s")

    resolved_input = _resolve_input_path(pos_input, input_path)
    result = _run_awl(resolved_input, dry_run=dry_run, verbose=verbose)
    _render_results(result, verbose, dry_run)
    try:
        _print_stdin_contents(resolved_input)
    except OSError as e:
        get_console().print(f"[red]Error reading temporary file: {e}[/red]")
        sys.exit(1)
