# awl — `__all__` Linter

**awl** is a lightweight utility that keeps your Python module’s `__all__` exports in sync with its imports.

It scans `__init__.py` files and automatically updates the `__all__` declaration based on the symbols you import — with support for comment-based control flags to ignore or include specific names. It also now supports **dry-run** and **diff** modes so you can preview changes before applying them.

---

## Features

- 🔍 Scans for imports in `__init__.py` files
- 🔄 Automatically updates or adds `__all__`
- 📁 Walks all source packages defined in `pyproject.toml`
- 🧵 Supports inline or file-level control via special comments:
  - `# awl:ignore` — skip file entirely
  - `# awl:include-private` — allow private names (e.g. `_foo`)
  - `# awl:exclude-public` — skip public names
- 📝 **Dry-run** mode (`--dry-run`) to show what would change without writing files
- 🔍 **Diff** mode (`--diff`) to print a unified diff of changes
- 🧘 No runtime dependencies

---

## Installation

```bash
pip install git+https://github.com/josephcourtney/awl.git
```

---

## Usage

### Single file

```bash
# Update __all__ in a specific file
awl path/to/package/__init__.py
```

### Whole project

```bash
# Discover pyproject.toml and update all __init__.py under source dirs
awl
```

### Verbose mode

Use `--verbose` or `-v` to print old and new `__all__` values for each file, even if no change is made.

```bash
awl --verbose
```

### Dry-run mode

Use `--dry-run` or `-d` to preview changes without writing them.

```bash
awl -d
```

### Combined

You can use both for a complete report without applying changes:

```bash
awl -d -v
```

---

## Control Flags

You can fine-tune what gets included with comment directives:

### File-level (top of file)

```python
# awl:ignore            # skip the file entirely
# awl:include-private   # allow private names (e.g. _foo)
# awl:exclude-public    # skip public names
```

### Line-level

```python
from .core import main  # awl:ignore
from .core import _helper  # awl:include-private
```

---

## License

GPLv3 © 2025 Joseph M. Courtney
