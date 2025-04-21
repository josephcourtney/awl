import ast
import tokenize
from pathlib import Path
from typing import Iterable

ALL_IGNORE = "all:ignore"
ALL_INCLUDE_PRIVATE = "all:include-private"
ALL_EXCLUDE_PUBLIC = "all:exclude-public"


def parse_control_flags(code: str) -> dict:
    lines = code.splitlines()
    file_flags = {
        "ignore_file": False,
        "include_private": False,
        "exclude_public": False,
    }
    line_flags = {}

    # File-level flags
    for line in lines[:5]:  # only look at top for file-wide comments
        if f"# {ALL_IGNORE}" in line:
            file_flags["ignore_file"] = True
        if f"# {ALL_INCLUDE_PRIVATE}" in line:
            file_flags["include_private"] = True
        if f"# {ALL_EXCLUDE_PUBLIC}" in line:
            file_flags["exclude_public"] = True

    # Line-level flags
    for lineno, line in enumerate(lines, 1):
        flags = set()
        if f"# {ALL_IGNORE}" in line:
            flags.add("ignore")
        if f"# {ALL_INCLUDE_PRIVATE}" in line:
            flags.add("include_private")
        if f"# {ALL_EXCLUDE_PUBLIC}" in line:
            flags.add("exclude_public")
        if flags:
            line_flags[lineno] = flags

    return {"file": file_flags, "lines": line_flags}


def find_public_names(tree: ast.Module, flags: dict, code_lines: list[str]) -> list[str]:
    names = set()
    file_flags = flags["file"]
    line_flags = flags["lines"]

    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue

        lineno = node.lineno
        local_flags = line_flags.get(lineno, set())

        if "ignore" in local_flags:
            continue

        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            is_private = name.startswith("_")

            allow_private = file_flags["include_private"] or "include_private" in local_flags
            exclude_public = file_flags["exclude_public"] or "exclude_public" in local_flags

            if is_private and not allow_private:
                continue
            if not is_private and exclude_public:
                continue

            names.add(name)

    return sorted(names)


def update_dunder_all(path: Path, new_all: Iterable[str]) -> None:
    code = path.read_text()
    tree = ast.parse(code)
    lines = code.splitlines()
    new_all_str = ", ".join(f'"{name}"' for name in sorted(new_all))

    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    start, end = node.lineno - 1, node.end_lineno
                    indent = " " * (len(lines[start]) - len(lines[start].lstrip()))
                    lines[start:end] = [f"{indent}__all__ = [{new_all_str}]"]
                    path.write_text("\n".join(lines) + "\n")
                    print(f"✅ Updated __all__ in {path}")
                    return

    # Append if no existing __all__ found
    lines.append(f"__all__ = [{new_all_str}]")
    path.write_text("\n".join(lines) + "\n")
    print(f"➕ Added __all__ to {path}")


def main(path: str = "src/clio/__init__.py"):
    p = Path(path)
    code = p.read_text()
    flags = parse_control_flags(code)

    if flags["file"]["ignore_file"]:
        print(f"🚫 Skipped {p} (file ignored by directive)")
        return

    tree = ast.parse(code)
    public_names = find_public_names(tree, flags, code.splitlines())
    update_dunder_all(p, public_names)
