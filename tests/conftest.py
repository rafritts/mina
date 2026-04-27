"""
Shared pytest fixtures and patches for all test modules.

Patches token_stats.record_response to a no-op so LLM mock tests don't
hit the real token stats file or fail on MagicMock serialization.
"""
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def pytest_addoption(parser):
    parser.addoption(
        "--user-accepts-token-spend",
        action="store_true",
        default=False,
        help="Required to run integration tests (invokes the LLM API)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--user-accepts-token-spend"):
        return
    skip = pytest.mark.skip(
        reason="invokes LLM API — re-run with --user-accepts-token-spend to proceed"
    )
    for item in items:
        if item.get_closest_marker("integration"):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def mock_token_stats():
    """Prevent any test from writing to the real token_stats.json or events.jsonl files."""
    with patch("src.application.infra.token_stats.record_response"), \
         patch("src.application.infra.token_stats.increment_turns"), \
         patch("src.application.infra.events.emit"), \
         patch("src.application.infra.events.emit_tool"):
        yield
