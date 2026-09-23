from __future__ import annotations

from pathlib import Path

import pytest

from kanbus import summarize


def test_completion_raises_missing_key_message_before_calling_litellm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KANBUS_TEST_AI_MOCK", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class ExplodingLiteLLM:
        def completion(self, **_kwargs: object) -> None:
            raise AssertionError("litellm.completion should not be called")

    monkeypatch.setattr(summarize, "litellm", ExplodingLiteLLM())

    with pytest.raises(RuntimeError, match="setup ai"):
        summarize._completion(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            issue_identifier="kanbus-1",
            operation="compaction_activity_summary",
            root=tmp_path,
            project_directory="project",
        )


def test_completion_skips_preflight_for_non_openai_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KANBUS_TEST_AI_MOCK", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    class FakeMessage:
        content = "A summary."

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]
        usage = None

    class FakeLiteLLM:
        def completion(self, **_kwargs: object) -> FakeResponse:
            return FakeResponse()

        def completion_cost(self, **_kwargs: object) -> float:
            return 0.0

    monkeypatch.setattr(summarize, "litellm", FakeLiteLLM())

    text = summarize._completion(
        model="anthropic/claude-3",
        messages=[{"role": "user", "content": "hi"}],
        issue_identifier="kanbus-2",
        operation="compaction_activity_summary",
        root=tmp_path,
        project_directory="project",
    )
    assert text == "A summary."


def test_completion_curates_authentication_errors_from_litellm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KANBUS_TEST_AI_MOCK", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "present-but-invalid")

    class AuthenticationError(Exception):
        pass

    class FakeLiteLLM:
        def completion(self, **_kwargs: object) -> None:
            raise AuthenticationError("invalid api_key provided")

    monkeypatch.setattr(summarize, "litellm", FakeLiteLLM())

    with pytest.raises(RuntimeError, match="setup ai"):
        summarize._completion(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            issue_identifier="kanbus-3",
            operation="compaction_activity_summary",
            root=tmp_path,
            project_directory="project",
        )


def test_completion_reraises_unrelated_errors_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KANBUS_TEST_AI_MOCK", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "present")

    class FakeLiteLLM:
        def completion(self, **_kwargs: object) -> None:
            raise ValueError("some unrelated failure")

    monkeypatch.setattr(summarize, "litellm", FakeLiteLLM())

    with pytest.raises(ValueError, match="some unrelated failure"):
        summarize._completion(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            issue_identifier="kanbus-4",
            operation="compaction_activity_summary",
            root=tmp_path,
            project_directory="project",
        )


def test_completion_mock_mode_bypasses_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("KANBUS_TEST_AI_MOCK", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    text = summarize._completion(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "hi"}],
        issue_identifier="kanbus-5",
        operation="compaction_activity_summary",
        root=tmp_path,
        project_directory="project",
    )
    assert "Mock activity summary" in text


def test_completion_raises_when_litellm_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("KANBUS_TEST_AI_MOCK", raising=False)
    monkeypatch.setattr(summarize, "litellm", None)

    with pytest.raises(RuntimeError, match="litellm package is not installed"):
        summarize._completion(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            issue_identifier="kanbus-6",
            operation="compaction_activity_summary",
            root=tmp_path,
            project_directory="project",
        )
