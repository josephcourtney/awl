import ast
from pathlib import Path
from typing import Iterable
import tomllib

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

    for line in lines[:5]:
        if f"# {ALL_IGNORE}" in line:
            file_flags["ignore_file"] = True
        if f"# {ALL_INCLUDE_PRIVATE}" in line:
            file_flags["include_private"] = True
        if f"# {ALL_EXCLUDE_PUBLIC}" in line:
            file_flags["exclude_public"] = True

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

def find_public_names(tree: ast.Module, flags: dict) -> list[str]:
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

def update_dunder_all(path: Path, new_all: Iterable[str]) -> bool:
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
                    old_line = "\n".join(lines[start:end])
                    new_line = f"{indent}__all__ = [{new_all_str}]"
                    if old_line.strip() == new_line.strip():
                        print(f"✅ {path} is up to date. Current __all__: [{new_all_str}]")
                        return False
                    lines[start:end] = [new_line]
                    path.write_text("\n".join(lines) + "\n")
                    print(f"🔁 Updated __all__ in {path}")
                    print("--- before ---")
                    print(old_line)
                    print("--- after ----")
                    print(new_line)
                    return True

    # __all__ not found
    lines.append(f"__all__ = [{new_all_str}]")
    path.write_text("\n".join(lines) + "\n")
    print(f"➕ Added __all__ to {path}")
    return True

def get_src_dirs(pyproject_path: Path) -> list[Path]:
    with pyproject_path.open("rb") as f:
        pyproject = tomllib.load(f)
    includes = pyproject.get("tool", {}).get("hatch", {}).get("build", {}).get("includes", [])
    roots = {Path(include).parts[0] for include in includes}
    return [Path("src") / root for root in roots]

def collect_init_files(base_dir: Path) -> list[Path]:
    return [p for p in base_dir.rglob("__init__.py")]

def main(path: str = None):
    if path is None:
        pyproject_path = Path("pyproject.toml")
        if not pyproject_path.exists():
            print("Error: no path given and no pyproject.toml found.")
            return
        src_dirs = get_src_dirs(pyproject_path)
        init_files = [f for src in src_dirs for f in collect_init_files(src)]
    else:
        init_files = [Path(path)]

    for file in init_files:
        code = file.read_text()
        flags = parse_control_flags(code)
        if flags["file"]["ignore_file"]:
            print(f"🚫 Skipped {file} (file ignored by directive)")
            continue
        tree = ast.parse(code)
        names = find_public_names(tree, flags)
        update_dunder_all(file, names)


