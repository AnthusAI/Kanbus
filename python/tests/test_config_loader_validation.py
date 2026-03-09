from __future__ import annotations

import copy
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from kanbus import config_loader
from kanbus.config import DEFAULT_CONFIGURATION
from kanbus.models import HookDefinition, ProjectConfiguration


def _base_config() -> ProjectConfiguration:
    return ProjectConfiguration.model_validate(copy.deepcopy(DEFAULT_CONFIGURATION))


def test_load_project_configuration_missing_file(tmp_path: Path) -> None:
    with pytest.raises(
        config_loader.ConfigurationError, match="configuration file not found"
    ):
        config_loader.load_project_configuration(tmp_path / ".kanbus.yml")


def test_load_project_configuration_merges_override_virtual_projects(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / ".kanbus.yml"
    config_path.write_text(
        "\n".join(
            [
                "project_key: main",
                "virtual_projects:",
                "  alpha:",
                "    path: alpha",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / ".kanbus.override.yml").write_text(
        "\n".join(
            [
                "virtual_projects:",
                "  beta:",
                "    path: beta",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    cfg = config_loader.load_project_configuration(config_path)
    assert set(cfg.virtual_projects.keys()) >= {"alpha", "beta"}


def test_load_project_configuration_unknown_and_validation_errors(
    tmp_path: Path,
) -> None:
    unknown_cfg = tmp_path / "unknown.yml"
    unknown_cfg.write_text("unknown_field: true\n", encoding="utf-8")
    with pytest.raises(
        config_loader.ConfigurationError, match="unknown configuration fields"
    ):
        config_loader.load_project_configuration(unknown_cfg)

    bad_cfg = tmp_path / "bad.yml"
    bad_cfg.write_text("project_key: []\n", encoding="utf-8")
    with pytest.raises(config_loader.ConfigurationError):
        config_loader.load_project_configuration(bad_cfg)


def test_load_project_configuration_raises_from_validation_errors(
    tmp_path: Path,
) -> None:
    bad_cfg = tmp_path / ".kanbus.yml"
    bad_cfg.write_text("project_directory: ''\n", encoding="utf-8")
    with pytest.raises(
        config_loader.ConfigurationError, match="project_directory must not be empty"
    ):
        config_loader.load_project_configuration(bad_cfg)


def test_load_project_configuration_validates_kanbus_yaml_type_workflow_bindings(
    tmp_path: Path,
) -> None:
    cfg = tmp_path / "kanbus.yml"
    cfg.write_text(
        "\n".join(
            [
                "hierarchy: [initiative, epic, issue, subtask]",
                "types: [custom]",
                "workflows:",
                "  default:",
                "    open: [closed]",
                "    closed: [open]",
                "statuses:",
                "  - key: open",
                "    name: Open",
                "    category: To do",
                "  - key: closed",
                "    name: Closed",
                "    category: Done",
                "categories:",
                "  - name: To do",
                "  - name: Done",
                "transition_labels:",
                "  default:",
                "    open:",
                "      closed: close",
                "    closed:",
                "      open: reopen",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(
        config_loader.ConfigurationError, match="missing workflow binding"
    ):
        config_loader.load_project_configuration(cfg)


def test_validate_type_workflow_bindings_collects_missing_types() -> None:
    cfg = _base_config()
    cfg.types = ["story", "missing"]
    cfg.workflows.pop("missing", None)

    errors = config_loader._validate_type_workflow_bindings(cfg)
    assert any("missing workflow binding" in e for e in errors)


def test_load_data_and_override_wrap_os_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "cfg.yml"
    cfg.write_text("project_key: x\n", encoding="utf-8")
    override = tmp_path / "override.yml"
    override.write_text("project_key: x\n", encoding="utf-8")

    original_read_text = Path.read_text

    def fake_read_text(path_self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        if path_self in {cfg, override}:
            raise OSError("boom")
        return original_read_text(path_self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    with pytest.raises(config_loader.ConfigurationError, match="boom"):
        config_loader._load_configuration_data(cfg)
    with pytest.raises(config_loader.ConfigurationError, match="boom"):
        config_loader._load_override_configuration(override)


def test_load_override_configuration_returns_empty_for_null_yaml(
    tmp_path: Path,
) -> None:
    override = tmp_path / ".kanbus.override.yml"
    override.write_text("null\n", encoding="utf-8")
    assert config_loader._load_override_configuration(override) == {}


def test_load_dotenv_missing_or_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_loader._load_dotenv(tmp_path / "missing.env")

    env_path = tmp_path / ".env"
    env_path.write_text("A=1\n", encoding="utf-8")
    monkeypatch.setattr(
        Path, "read_text", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("x"))
    )
    config_loader._load_dotenv(env_path)


def test_validate_project_configuration_error_paths() -> None:
    cfg = _base_config()
    cfg.project_directory = ""
    cfg.wiki_directory = "/absolute"
    cfg.virtual_projects = {cfg.project_key: cfg.virtual_projects.get(cfg.project_key) or type("VP", (), {"path": "x"})()}  # type: ignore[assignment]
    cfg.new_issue_project = "missing"
    cfg.hierarchy = []
    cfg.workflows = {}
    cfg.default_priority = 999
    cfg.categories = []
    cfg.statuses = []

    errors = config_loader.validate_project_configuration(cfg)
    joined = " | ".join(errors)
    assert "project_directory must not be empty" in joined
    assert "wiki_directory must not escape project root" in joined
    assert "virtual project label conflicts with project key" in joined
    assert "new_issue_project references unknown project" in joined
    assert "hierarchy must not be empty" in joined
    assert "default workflow is required" in joined
    assert "default priority must be in priorities map" in joined
    assert "categories must not be empty" in joined
    assert "statuses must not be empty" in joined


def test_validate_project_configuration_status_workflow_and_transition_errors() -> None:
    cfg = _base_config()
    cfg.categories = cfg.categories[:1]
    cfg.statuses[0].category = "Missing"
    cfg.statuses[1].key = cfg.statuses[0].key
    cfg.initial_status = "missing"
    cfg.workflows = {"default": {"nope": ["also_nope"]}}
    cfg.transition_labels = {"default": {"nope": {"wrong": "x"}, "extra": {"x": "y"}}}

    errors = config_loader.validate_project_configuration(cfg)
    joined = " | ".join(errors)
    assert "references undefined category" in joined
    assert "duplicate status key" in joined
    assert "must exist in statuses" in joined
    assert "references undefined status" in joined
    assert "missing from-status" in joined or "missing transition" in joined
    assert "references invalid from-status" in joined


def test_validate_project_configuration_additional_duplicate_and_wiki_paths() -> None:
    cfg = _base_config()
    cfg.wiki_directory = "..\\..\\outside"
    cfg.hierarchy = ["initiative", "initiative"]
    cfg.categories[1].name = cfg.categories[0].name
    cfg.statuses[1].name = cfg.statuses[0].name

    errors = config_loader.validate_project_configuration(cfg)
    joined = " | ".join(errors)
    assert "wiki_directory must not escape project root" in joined
    assert "duplicate type name" in joined
    assert "duplicate category name" in joined
    assert "duplicate status name" in joined


def test_validate_project_configuration_transition_labels_missing_workflow() -> None:
    cfg = _base_config()
    cfg.transition_labels = {}

    errors = config_loader.validate_project_configuration(cfg)
    assert "transition_labels must not be empty" in " | ".join(errors)


def test_validate_project_configuration_transition_label_missing_paths() -> None:
    cfg = _base_config()
    cfg.transition_labels = {"default": {"open": {"backlog": "x"}}}
    cfg.workflows = {"default": {"open": ["closed"]}}
    errors = config_loader.validate_project_configuration(cfg)
    joined = " | ".join(errors)
    assert "missing transition 'open' -> 'closed'" in joined
    assert "references invalid transition 'open' -> 'backlog'" in joined

    cfg.transition_labels = {"default": {"open": {}}}
    errors = config_loader.validate_project_configuration(cfg)
    assert "missing from-status" in " | ".join(errors)

    cfg.transition_labels = {"default": {"open": {"closed": "x"}}}
    cfg.workflows = {"default": {"open": ["closed"]}, "epic": {"open": ["closed"]}}
    errors = config_loader.validate_project_configuration(cfg)
    assert "transition_labels missing workflow 'epic'" in " | ".join(errors)


def test_validate_hooks_and_sort_order_paths() -> None:
    cfg = _base_config()
    cfg.hooks.before = {
        "unknown.event": [
            HookDefinition.model_validate({"id": "h1", "command": ["echo"]})
        ],
        "issue.create": [],
    }
    cfg.hooks.after = {
        "issue.update": [
            HookDefinition.model_validate({"id": "dup", "command": ["echo"]}),
            HookDefinition.model_validate({"id": "dup", "command": ["echo"]}),
        ]
    }
    cfg.sort_order = {
        "categories": {1: "fifo"},
        "open": [{"field": "priority", "direction": "asc", "extra": "x"}],
    }

    errors = config_loader.validate_project_configuration(cfg)
    joined = " | ".join(errors)
    assert "contains unknown event" in joined
    assert "must define at least one hook" in joined
    assert "has duplicate id" in joined
    assert "sort_order.categories keys must be strings" in joined
    assert "unsupported key 'extra'" in joined


def test_validate_sort_order_non_mapping_categories() -> None:
    cfg = _base_config()
    cfg.sort_order = {"categories": "fifo"}
    errors = config_loader.validate_project_configuration(cfg)
    assert "sort_order.categories must be a mapping" in " | ".join(errors)


def test_validate_sort_order_category_rule_is_validated() -> None:
    cfg = _base_config()
    cfg.sort_order = {"categories": {"To do": []}}
    errors = config_loader.validate_project_configuration(cfg)
    assert "sort_order.categories.To do must not be an empty list" in " | ".join(errors)


def test_validate_sort_rule_non_list_and_empty_and_non_dict() -> None:
    errors: list[str] = []
    config_loader._validate_sort_rule("x", 1, errors)
    config_loader._validate_sort_rule("x", [], errors)
    config_loader._validate_sort_rule("x", ["bad"], errors)
    joined = " | ".join(errors)
    assert "must be a preset string or a list" in joined
    assert "must not be an empty list" in joined
    assert "must be an object with field/direction" in joined


def test_validate_sort_rule_non_string_key_message() -> None:
    errors: list[str] = []
    config_loader._validate_sort_rule(
        "x", [{1: "bad", "field": "priority", "direction": "asc"}], errors
    )
    assert "contains a non-string key" in " | ".join(errors)


def test_reject_legacy_fields_preserves_virtual_projects_when_present() -> None:
    data = {
        "virtual_projects": {"x": {"path": "x"}},
        "external_projects": {"y": {"path": "y"}},
    }
    config_loader._reject_legacy_fields(data)
    assert data["virtual_projects"] == {"x": {"path": "x"}}
    assert "external_projects" not in data


def test_has_unknown_fields_false_case() -> None:
    class Model(BaseModel):
        count: int

    try:
        Model.model_validate({"count": "bad"})
    except ValidationError as error:
        assert config_loader._has_unknown_fields(error) is False
    else:
        raise AssertionError("expected validation error")
