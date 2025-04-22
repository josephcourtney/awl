import ast
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import TypedDict


class ProcessResult(TypedDict, total=False):
    status: str
    reason: str
    file: Path
    old_all: list[str]
    new_all: list[str]


AWL_DIRECTIVES = {
    "ignore_file": "awl:ignore",
    "include_private": "awl:include-private",
    "exclude_public": "awl:exclude-public",
}


class ImportFilter:
    def __init__(self, flags: dict):
        self.file_flags = flags["file"]
        self.line_flags = flags["lines"]

    def should_include(self, name: str, lineno: int) -> bool:
        is_private = name.startswith("_")
        line = self.line_flags.get(lineno, set())

        if "ignore" in line:
            return False
        if is_private and not (self.file_flags["include_private"] or "include_private" in line):
            return False
        return not (not is_private and (self.file_flags["exclude_public"] or "exclude_public" in line))


def parse_control_flags(code: str) -> dict:
    lines = code.splitlines()
    file_flags = {"ignore_file": False, "include_private": False, "exclude_public": False}
    line_flags: dict[int, set[str]] = {}

    for line in lines[:5]:
        if f"# {AWL_DIRECTIVES['ignore_file']}" in line:
            file_flags["ignore_file"] = True
        if f"# {AWL_DIRECTIVES['include_private']}" in line:
            file_flags["include_private"] = True
        if f"# {AWL_DIRECTIVES['exclude_public']}" in line:
            file_flags["exclude_public"] = True

    for lineno, line in enumerate(lines, 1):
        flags: set[str] = set()
        if f"# {AWL_DIRECTIVES['ignore_file']}" in line:
            flags.add("ignore")
        if f"# {AWL_DIRECTIVES['include_private']}" in line:
            flags.add("include_private")
        if f"# {AWL_DIRECTIVES['exclude_public']}" in line:
            flags.add("exclude_public")
        if flags:
            line_flags[lineno] = flags

    return {"file": file_flags, "lines": line_flags}


def find_public_names(tree: ast.Module, flags: dict) -> list[str]:
    names: set[str] = set()
    name_filter = ImportFilter(flags)

    for node in tree.body:
        if not isinstance(node, ast.Import | ast.ImportFrom):
            continue
        lineno = node.lineno
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            if name_filter.should_include(name, lineno):
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


def _format_new_block(indent: str, new_all: list[str], max_line_length: int = 120) -> str:
    inline = f"{indent}__all__ = [{', '.join(f'"{name}"' for name in new_all)}]\n"
    if len(inline) <= max_line_length:
        return inline

    multiline = f"{indent}__all__ = [\n"
    multiline += "".join(f'{indent}    "{name}",\n' for name in new_all)
    multiline += f"{indent}]\n"
    return multiline


def update_dunder_all(
    path: Path,
    new_all: Iterable[str],
    *,
    dry_run: bool = False,
) -> tuple[bool, str | None]:
    code = path.read_text()
    tree = ast.parse(code)
    lines = code.splitlines(keepends=True)
    sorted_all = sorted(new_all)

    assigns = _find_all_node(tree)
    if len(assigns) > 1:
        return False, "Multiple __all__ assignments"

    old_block = None
    new_lines = lines.copy()

    if assigns:
        node = assigns[0]
        start, end = node.lineno - 1, node.end_lineno
        indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
        new_block = _format_new_block(indent, sorted_all)
        old_block = "".join(lines[start:end])
        if old_block == new_block:
            return False, None
        new_lines[start:end] = [new_block]
    else:
        new_block = _format_new_block("", sorted_all)
        new_lines.append(new_block)

    if not dry_run:
        path.write_text("".join(new_lines))

    return True, None


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


def extract_current_all(tree: ast.Module) -> list[str] | None:
    assigns = _find_all_node(tree)
    if not assigns:
        return None
    try:
        all_node = assigns[0].value
        if isinstance(all_node, (ast.List | ast.Tuple)):
            return [elt.value for elt in all_node.elts if isinstance(elt, ast.Constant)]
    except (AttributeError, ValueError, TypeError):
        return None
    return None


def process_file(
    file_path: Path,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> ProcessResult:
    code = file_path.read_text()
    tree = ast.parse(code)

    if any(
        isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)
        for node in tree.body
    ):
        return {"status": "skip", "reason": "wildcard", "file": file_path}

    flags = parse_control_flags(code)
    if flags["file"]["ignore_file"]:
        return {"status": "skip", "reason": "ignore", "file": file_path}

    public_names = find_public_names(tree, flags)
    old_all = extract_current_all(tree) if verbose else None

    changed, reason = update_dunder_all(file_path, public_names, dry_run=dry_run)

    return {
        "status": "changed" if changed else "unchanged",
        "file": file_path,
        "old_all": old_all,
        "new_all": public_names,
        "reason": reason,
    }


def main(
    path: str | None = None,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> list[ProcessResult]:
    if path is None:
        pyproject_path = Path("pyproject.toml")
        if not pyproject_path.exists():
            return [{"status": "error", "reason": "no-pyproject"}]

        files_to_process = []
        for src in get_src_dirs(pyproject_path):
            files_to_process.extend(collect_init_files(src))
    else:
        files_to_process = [Path(path)]

    return [process_file(file_path, dry_run=dry_run, verbose=verbose) for file_path in files_to_process]
