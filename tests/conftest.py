import re
import sys
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

import awl.cli

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

MAX_OUTPUT_LINES = 32


@pytest.fixture
def strip_ansi():
    return lambda text: re.sub(r"\x1b\[[0-9;]*m", "", text)


@pytest.fixture(autouse=True)
def patch_console(monkeypatch):
    """Patch the rich Console to capture output during CLI tests."""
    stream = StringIO()
    console = Console(file=stream, force_terminal=True, color_system="truecolor")

    # Patch only the CLI module

    monkeypatch.setattr(awl.cli, "_default_console", console)
    monkeypatch.setattr(awl.cli, "get_console", lambda: console)

    return stream


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Limit captured output per test."""
    if report.when == "call" and report.failed:
        new_sections = []
        for title, content in report.sections:
            if title.startswith(("Captured stdout", "Captured stderr")):
                lines = content.splitlines()
                if len(lines) > MAX_OUTPUT_LINES:
                    truncated = "\n".join([*lines[:MAX_OUTPUT_LINES], "... [output truncated]"])
                    new_sections.append((title, truncated))
                else:
                    new_sections.append((title, content))
            else:
                new_sections.append((title, content))
        report.sections = new_sections
