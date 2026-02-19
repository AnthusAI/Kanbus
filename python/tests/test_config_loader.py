import json
from pathlib import Path

import pytest

from kanbus.config_loader import ConfigurationError, load_project_configuration


def test_load_valid_config(tmp_path: Path):
    config = {"project_key": "tsk"}  # rely on defaults for the rest
    path = tmp_path / "kanbus.yml"
    path.write_text(json.dumps(config))

    result = load_project_configuration(path)
    assert result.project_key == "tsk"
    assert result.project_directory == "project"
    # Defaults remain intact
    assert "initiative" in result.hierarchy


def test_load_missing_file(tmp_path: Path):
    missing = tmp_path / "kanbus.yml"
    with pytest.raises(ConfigurationError):
        load_project_configuration(missing)
