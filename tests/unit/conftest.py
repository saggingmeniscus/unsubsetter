"""Unit-test configuration: patch expensive I/O for speed."""
from __future__ import annotations
from pathlib import Path
import unittest.mock as mock

import pytest


@pytest.fixture(autouse=True)
def _fast_font_search_paths(monkeypatch):
    """Replace the default TeX-Live-aware search paths with a single cheap dir.

    Unit tests must not scan thousands of TeX Live fonts.  They exercise logic,
    not font-file discovery.  Integration tests (in tests/integration/) are free
    to use the real paths.
    """
    # Patch both the source module and the name imported into the CLI module.
    monkeypatch.setattr(
        "unsubsetter.font_index.default_search_paths",
        lambda: [Path("/Library/Fonts")],
    )
    # The CLI does `from unsubsetter.font_index import default_search_paths`,
    # so we must also patch the name bound in the CLI module's namespace.
    import unsubsetter.cli  # ensure it is imported before patching
    monkeypatch.setattr(
        unsubsetter.cli,
        "default_search_paths",
        lambda: [Path("/Library/Fonts")],
    )
