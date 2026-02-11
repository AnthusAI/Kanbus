"""
Placeholder test to keep pytest collection green.
"""


def test_placeholder_passes() -> None:
    """Ensure pytest has at least one passing test."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

    from taskulus import __version__

    assert __version__ == "0.1.0"
