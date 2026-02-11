"""
Pytest configuration for shared Gherkin feature discovery.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

FEATURES_BASE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "specs", "features")
)
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC_DIR))


def pytest_configure(config: object) -> None:
    """
    Configure pytest-bdd to use shared feature files.

    :param config: Pytest configuration object.
    :type config: object
    """
    config.option.bdd_features_base_dir = FEATURES_BASE_DIR
