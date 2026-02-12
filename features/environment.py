"""Behave environment proxy for shared features."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_environment_module():
    root = Path(__file__).resolve().parents[1]
    env_path = root / "python" / "features" / "environment.py"
    spec = importlib.util.spec_from_file_location("taskulus_behave_environment", env_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load environment module: {env_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


env_module = _load_environment_module()


def before_scenario(context: object, scenario: object) -> None:
    env_module.before_scenario(context, scenario)


def after_scenario(context: object, scenario: object) -> None:
    env_module.after_scenario(context, scenario)
