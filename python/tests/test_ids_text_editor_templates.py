from __future__ import annotations

from pathlib import Path

import pytest

from kanbus import ids, project_management_template, text_editor, wiki_templates


def test_id_uuid_sequence_and_generation() -> None:
    ids.set_test_uuid_sequence(["abc123", "def456"])
    assert ids._next_uuid_value() == "abc123"
    assert ids._next_uuid_value() == "def456"
    ids.set_test_uuid_sequence(None)

    req = ids.IssueIdentifierRequest(title="x", prefix="kanbus", existing_ids=set())
    result = ids.generate_issue_identifier(req)
    assert result.identifier.startswith("kanbus-")


def test_format_issue_key_variants() -> None:
    assert ids.format_issue_key("12345", project_context=False) == "12345"
    assert (
        ids.format_issue_key("kanbus-abcdef123456", project_context=False)
        == "kanbus-abcdef"
    )
    assert ids.format_issue_key("kanbus-abcdef123456", project_context=True) == "abcdef"
    assert (
        ids.format_issue_key("kanbus-abcdef123456.2", project_context=False)
        == "kanbus-abcdef.2"
    )
    assert ids.format_issue_key("abcdef123456", project_context=False) == "abcdef"


def test_matches_issue_identifier_paths() -> None:
    full = "kanbus-abcdef123456"
    assert ids.matches_issue_identifier(full, full) is True
    assert (
        ids.matches_issue_identifier(
            ids.format_issue_key(full, project_context=False), full
        )
        is True
    )
    assert (
        ids.matches_issue_identifier(
            ids.format_issue_key(full, project_context=True), full
        )
        is True
    )
    assert ids.matches_issue_identifier("x" * len(full), full) is False
    assert ids.matches_issue_identifier("kanbus-ab", full) is True
    assert ids.matches_issue_identifier("zzz", full) is False


def test_generate_issue_identifier_collision_failure() -> None:
    ids.set_test_uuid_sequence(["dup"] * 10)
    req = ids.IssueIdentifierRequest(
        title="x", prefix="kanbus", existing_ids={"kanbus-dup"}
    )
    with pytest.raises(RuntimeError, match="unable to generate unique id"):
        ids.generate_issue_identifier(req)
    ids.set_test_uuid_sequence(None)


def test_generate_many_identifiers() -> None:
    ids.set_test_uuid_sequence(["a", "b", "c"])
    generated = ids.generate_many_identifiers("title", "kanbus", 3)
    assert generated == {"kanbus-a", "kanbus-b", "kanbus-c"}
    ids.set_test_uuid_sequence(None)


def test_text_editor_view_and_directory(tmp_path: Path) -> None:
    root = tmp_path
    subdir = root / "d"
    subdir.mkdir()
    (subdir / "z.txt").write_text("z", encoding="utf-8")
    (subdir / "a").mkdir()

    listing = text_editor.edit_view(root, Path("d"))
    assert listing.splitlines() == ["a/", "z.txt"]

    file_path = root / "file.txt"
    file_path.write_text("one\ntwo\nthree\n", encoding="utf-8")
    viewed = text_editor.edit_view(root, Path("file.txt"))
    assert "1: one" in viewed
    ranged = text_editor.edit_view(root, Path("file.txt"), view_range=(2, -1))
    assert ranged == "2: two\n3: three"
    from_zero = text_editor.edit_view(root, Path("file.txt"), view_range=(0, 1))
    assert from_zero == "1: one"


def test_text_editor_view_errors(tmp_path: Path) -> None:
    root = tmp_path
    with pytest.raises(text_editor.TextEditorError, match="escapes repository root"):
        text_editor.edit_view(root, Path("../x"))
    with pytest.raises(
        text_editor.TextEditorError, match="file or directory not found"
    ):
        text_editor.edit_view(root, Path("missing.txt"))


def test_text_editor_str_replace_paths(tmp_path: Path) -> None:
    root = tmp_path
    file_path = root / "replace.txt"
    file_path.write_text("hello world", encoding="utf-8")

    assert "Successfully replaced" in text_editor.edit_str_replace(
        root, Path("replace.txt"), "hello", "hi"
    )
    assert file_path.read_text(encoding="utf-8") == "hi world"

    with pytest.raises(text_editor.TextEditorError, match="escapes repository root"):
        text_editor.edit_str_replace(root, Path("../x"), "a", "b")
    with pytest.raises(text_editor.TextEditorError, match="file not found"):
        text_editor.edit_str_replace(root, Path("missing.txt"), "a", "b")

    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(text_editor.TextEditorError, match="no match found"):
        text_editor.edit_str_replace(root, Path("replace.txt"), "a", "b")

    file_path.write_text("x\nx", encoding="utf-8")
    with pytest.raises(text_editor.TextEditorError, match="found 2 matches"):
        text_editor.edit_str_replace(root, Path("replace.txt"), "x", "y")


def test_text_editor_create_and_insert(tmp_path: Path) -> None:
    root = tmp_path
    created = text_editor.edit_create(root, Path("new/file.txt"), "hello")
    assert "Successfully created file" in created
    assert (root / "new" / "file.txt").read_text(encoding="utf-8") == "hello"

    with pytest.raises(text_editor.TextEditorError, match="escapes repository root"):
        text_editor.edit_create(root, Path("../x"), "x")
    with pytest.raises(text_editor.TextEditorError, match="file already exists"):
        text_editor.edit_create(root, Path("new/file.txt"), "x")

    target = root / "insert.txt"
    target.write_text("a\nb\n", encoding="utf-8")
    assert "Successfully inserted" in text_editor.edit_insert(
        root, Path("insert.txt"), 1, "x"
    )
    assert target.read_text(encoding="utf-8") == "a\nx\nb\n"

    empty = root / "empty.txt"
    empty.write_text("", encoding="utf-8")
    text_editor.edit_insert(root, Path("empty.txt"), 0, "")
    assert empty.read_text(encoding="utf-8") == ""

    with pytest.raises(text_editor.TextEditorError, match="escapes repository root"):
        text_editor.edit_insert(root, Path("../x"), 0, "x")
    with pytest.raises(text_editor.TextEditorError, match="file not found"):
        text_editor.edit_insert(root, Path("missing.txt"), 0, "x")
    with pytest.raises(text_editor.TextEditorError, match="non-negative"):
        text_editor.edit_insert(root, Path("insert.txt"), -1, "x")
    with pytest.raises(text_editor.TextEditorError, match="exceeds file length"):
        text_editor.edit_insert(root, Path("insert.txt"), 999, "x")


def test_template_constants_are_expected() -> None:
    assert wiki_templates.DEFAULT_WIKI_INDEX_FILENAME == "index.md"
    assert wiki_templates.DEFAULT_WIKI_WHATS_NEXT_FILENAME == "whats-next.md"
    assert "What's Next" in wiki_templates.DEFAULT_WIKI_INDEX
    assert 'query(status="open"' in wiki_templates.DEFAULT_WIKI_WHATS_NEXT

    assert project_management_template.DEFAULT_PROJECT_MANAGEMENT_TEMPLATE_FILENAME.endswith(
        ".template.md"
    )
    assert (
        "This is The Way."
        in project_management_template.DEFAULT_PROJECT_MANAGEMENT_TEMPLATE
    )
    assert (
        "{{ project_key }}"
        in project_management_template.DEFAULT_PROJECT_MANAGEMENT_TEMPLATE
    )
