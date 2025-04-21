# awl — `__all__` Linter

**awl** is a lightweight utility that keeps your Python module’s `__all__` exports in sync with its imports.

It scans `__init__.py` files and automatically updates the `__all__` declaration based on the symbols you import — with support for comment-based control flags to ignore or include specific names. It also now supports **dry-run** and **diff** modes so you can preview changes before applying them.

---

## Features

- 🔍 Scans for imports in `__init__.py` files
- 🔄 Automatically updates or adds `__all__`
- 📁 Walks all source packages defined in `pyproject.toml`
- 🧵 Supports inline or file-level control via special comments:
  - `# all:ignore` — skip file entirely
  - `# all:include-private` — allow private names (e.g. `_foo`)
  - `# all:exclude-public` — skip public names
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

### Preview changes (dry-run)

```bash
# Show what updates would happen, without writing files
awl --dry-run
```

### Show diffs

```bash
# Print unified diff of changes; writes files unless --dry-run is also used
awl --diff
```

You can also combine flags:

```bash
# Preview diffs without writing
awl --dry-run --diff
```

---

## Control Flags

You can fine-tune what gets included with comment directives:

### File-level (top of file)

```python
# all:ignore            # skip the file entirely
# all:include-private   # allow private names (e.g. _foo)
# all:exclude-public    # skip public names
```

### Line-level

```python
from .core import main  # all:ignore
from .core import _helper  # all:include-private
```

---

## License

GPLv3 © 2025 Joseph M. Courtney
