"""Pytest configuration and shared fixtures."""

import pytest


@pytest.fixture
def sample_assumptions():
    return {
        "x": {"real": True},
        "y": {"real": True},
        "n": {"integer": True, "positive": True},
    }
