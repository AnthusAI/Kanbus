"""Load Python step definitions for Behave from the implementation folder."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_python_steps() -> None:
    root = Path(__file__).resolve().parents[2]
    python_dir = root / "python"
    python_steps = python_dir / "features" / "steps"
    sys.path.insert(0, str(python_dir))
    sys.path.insert(0, str(python_dir / "src"))

    for path in sorted(python_steps.glob("*.py")):
        if path.name == "__init__.py":
            continue
        module_name = f"kanbus_behave_steps.{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"unable to load step module: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)


_load_python_steps()
