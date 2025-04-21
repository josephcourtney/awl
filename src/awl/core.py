import ast
import difflib
import tomllib
from collections.abc import Iterable
from pathlib import Path

ALL_IGNORE = "all:ignore"
ALL_INCLUDE_PRIVATE = "all:include-private"
ALL_EXCLUDE_PUBLIC = "all:exclude-public"


def parse_control_flags(code: str) -> dict:
    lines = code.splitlines()
    file_flags = {"ignore_file": False, "include_private": False, "exclude_public": False}
    line_flags: dict[int, set[str]] = {}

    for line in lines[:5]:
        if f"# {ALL_IGNORE}" in line:
            file_flags["ignore_file"] = True
        if f"# {ALL_INCLUDE_PRIVATE}" in line:
            file_flags["include_private"] = True
        if f"# {ALL_EXCLUDE_PUBLIC}" in line:
            file_flags["exclude_public"] = True

    for lineno, line in enumerate(lines, 1):
        flags: set[str] = set()
        if f"# {ALL_IGNORE}" in line:
            flags.add("ignore")
        if f"# {ALL_INCLUDE_PRIVATE}" in line:
            flags.add("include_private")
        if f"# {ALL_EXCLUDE_PUBLIC}" in line:
            flags.add("exclude_public")
        if flags:
            line_flags[lineno] = flags

    return {"file": file_flags, "lines": line_flags}


def find_public_names(tree: ast.Module, flags: dict) -> list[str]:
    names: set[str] = set()
    file_flags = flags["file"]
    line_flags = flags["lines"]

    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        lineno = node.lineno
        if "ignore" in line_flags.get(lineno, set()):
            continue

        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            is_private = name.startswith("_")
            allow_private = file_flags["include_private"] or "include_private" in line_flags.get(
                lineno, set()
            )
            exclude_public = file_flags["exclude_public"] or "exclude_public" in line_flags.get(lineno, set())
            if (is_private and not allow_private) or (not is_private and exclude_public):
                continue
            names.add(name)

    return sorted(names)


def _find_all_node(tree: ast.Module) -> list[ast.Assign]:
    return [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id == "__all__"
    ]


def _format_new_block(indent: str, new_all_str: str) -> str:
    return f"{indent}__all__ = [{new_all_str}]\n"


def _print_diff(path: Path, old_lines: list[str], new_lines: list[str]) -> None:
    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=str(path),
        tofile=str(path) + " (new)",
        lineterm="",
    )
    print("\n".join(diff))


def update_dunder_all(
    path: Path,
    new_all: Iterable[str],
    *,
    dry_run: bool = False,
    show_diff: bool = False,
) -> bool:
    """
    Update (or add) the __all__ assignment in `path`.

    If dry_run is True, do not write—just report.
    If show_diff is True, print a unified diff between old and new.

    Returns True if a change *would* be (or was) made.
    """
    code = path.read_text()
    tree = ast.parse(code)
    lines = code.splitlines(keepends=True)
    new_all_str = ", ".join(f'"{name}"' for name in sorted(new_all))

    assigns = _find_all_node(tree)
    if len(assigns) > 1:
        print(f"⚠️  Multiple __all__ assignments in {path}; aborting without changes.")
        return False

    old_block = None
    new_lines = lines.copy()

    if assigns:
        node = assigns[0]
        start, end = node.lineno - 1, node.end_lineno
        indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
        new_block = _format_new_block(indent, new_all_str)
        old_block = "".join(lines[start:end])
        if old_block == new_block:
            print(f"✅ {path} is up to date. Current __all__: [{new_all_str}]")
            return False
        new_lines[start:end] = [new_block]
    else:
        new_block = _format_new_block("", new_all_str)
        new_lines.append(new_block)

    if show_diff or dry_run:
        _print_diff(path, lines, new_lines)

    if not dry_run:
        path.write_text("".join(new_lines))
        action = "🔁 Updated" if old_block else "+ Added"
        print(f"{action} __all__ in {path}")
    else:
        print(f"📝 Dry run: no changes written to {path}")

    return True


def get_src_dirs(pyproject_path: Path) -> list[Path]:
    with pyproject_path.open("rb") as f:
        pyproject = tomllib.load(f)
    includes = pyproject.get("tool", {}).get("hatch", {}).get("build", {}).get("includes", [])
    dirs: list[Path] = []
    for inc in includes:
        p = Path(inc)
        parts: list[str] = []
        for part in p.parts:
            if "*" in part or "?" in part:
                break
            parts.append(part)
        if parts:
            dirs.append(Path(*parts))
    return dirs


def collect_init_files(base_dir: Path) -> list[Path]:
    return list(base_dir.rglob("__init__.py"))


def main(
    path: str | None = None,
    *,
    dry_run: bool = False,
    show_diff: bool = False,
) -> None:
    if path is None:
        pyproject_path = Path("pyproject.toml")
        if not pyproject_path.exists():
            print("Error: no path given and no pyproject.toml found.")
            return
        files_to_process: list[Path] = []
        for src in get_src_dirs(pyproject_path):
            files_to_process.extend(collect_init_files(src))
    else:
        files_to_process = [Path(path)]

    for file_path in files_to_process:
        code = file_path.read_text()
        tree = ast.parse(code)

        # wildcard import → skip
        if any(
            isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
            for node in tree.body
        ):
            print(f"⚠️  Wildcard import in {file_path}; skipping.")
            continue

        flags = parse_control_flags(code)
        if flags["file"]["ignore_file"]:
            print(f"🚫 Skipped {file_path} (file ignored by directive)")
            continue

        names = find_public_names(tree, flags)
        update_dunder_all(file_path, names, dry_run=dry_run, show_diff=show_diff)
