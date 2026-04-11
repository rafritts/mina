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


@pytest.fixture(autouse=True)
def mock_token_stats():
    """Prevent any test from writing to the real token_stats.json file."""
    with patch("token_stats.record_response"), \
         patch("token_stats.increment_turns"):
        yield
