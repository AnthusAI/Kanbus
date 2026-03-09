from kanbus.github_security_sync import (
    _extract_repo_slug,
    _parse_next_link,
    _severity_to_priority,
)


def test_extract_repo_slug() -> None:
    assert (
        _extract_repo_slug("https://github.com/AnthusAI/Kanbus.git")
        == "AnthusAI/Kanbus"
    )
    assert _extract_repo_slug("git@github.com:AnthusAI/Kanbus.git") == "AnthusAI/Kanbus"
    assert _extract_repo_slug("ssh://gitlab.com/foo/bar.git") is None


def test_parse_next_link() -> None:
    header = (
        '<https://api.github.com/foo?page=2>; rel="next", '
        '<https://api.github.com/foo?page=3>; rel="last"'
    )
    assert _parse_next_link(header) == "https://api.github.com/foo?page=2"
    assert _parse_next_link('<https://api.github.com/foo?page=3>; rel="last"') is None


def test_severity_to_priority() -> None:
    assert _severity_to_priority("critical") == 0
    assert _severity_to_priority("high") == 1
    assert _severity_to_priority("medium") == 2
    assert _severity_to_priority("low") == 3
    assert _severity_to_priority("unknown") == 3
