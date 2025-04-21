"""Entry-point module, invoked with `python -m biscotti`.

Why does this file exist, and why __main__? For more info, read:
- https://www.python.org/dev/peps/pep-0338/
- https://docs.python.org/3/using/cmdline.html#cmdoption-m
"""

import sys

from awl.cli import main

if __name__ == "__main__":
    status: int = main()
    sys.exit(status)
