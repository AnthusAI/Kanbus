"""
Placeholder test to keep pytest collection green.
"""


def test_placeholder_passes() -> None:
    """Ensure pytest has at least one passing test."""
    from taskulus import __version__

    assert __version__ == "0.1.0"
