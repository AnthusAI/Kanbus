"""Tests for tools/check_console_blocking_io.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def load_checker_module() -> ModuleType:
    """
    Load the checker tool as a module.

    :return: The imported tool module.
    :rtype: ModuleType
    """
    specification = importlib.util.spec_from_file_location(
        "check_console_blocking_io",
        REPOSITORY_ROOT / "tools" / "check_console_blocking_io.py",
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


checker = load_checker_module()


def descriptions(source: str) -> list:
    """
    Return violation descriptions for a Rust snippet.

    :param source: Rust source text.
    :type source: str
    :return: Violation descriptions in source order.
    :rtype: list
    """
    return [item.description for item in checker.check_source("sample.rs", source)]


def test_flags_direct_std_fs_call_in_async_handler() -> None:
    source = """
async fn handler() -> String {
    std::fs::read_to_string("a.txt").unwrap()
}
"""
    assert descriptions(source) == ["read_to_string", "std::fs call"]


def test_allows_blocking_call_inside_spawn_blocking() -> None:
    source = """
async fn handler() -> String {
    tokio::task::spawn_blocking(move || std::fs::read_to_string("a.txt").unwrap())
        .await
        .unwrap()
}
"""
    assert descriptions(source) == []


def test_allows_blocking_call_inside_run_blocking_wrapper() -> None:
    source = """
async fn handler() {
    run_blocking(move || Ok(std::fs::read("a")?)).await;
}
"""
    assert descriptions(source) == []


def test_ignores_blocking_calls_in_synchronous_functions() -> None:
    source = """
fn helper() -> String {
    std::fs::read_to_string("a.txt").unwrap()
}
"""
    assert descriptions(source) == []


def test_flags_async_call_to_blocking_synchronous_helper() -> None:
    source = """
fn load_asset() -> Vec<u8> {
    std::fs::read("a").unwrap()
}

fn wrapper() -> Vec<u8> {
    load_asset()
}

async fn handler() -> Vec<u8> {
    wrapper()
}
"""
    assert descriptions(source) == ["call to blocking helper function"]


def test_allows_blocking_helper_called_inside_spawn_blocking() -> None:
    source = """
fn load_asset() -> Vec<u8> {
    std::fs::read("a").unwrap()
}

async fn handler() -> Vec<u8> {
    tokio::task::spawn_blocking(|| load_asset()).await.unwrap()
}
"""
    assert descriptions(source) == []


def test_flags_blocking_call_in_async_block() -> None:
    source = """
fn start() {
    tokio::spawn(async move {
        std::thread::sleep(std::time::Duration::from_secs(1));
    });
}
"""
    assert descriptions(source) == ["thread::sleep"]


def test_flags_process_and_path_metadata_calls() -> None:
    source = """
async fn handler(path: std::path::PathBuf) {
    let _ = Command::new("git").output();
    let _ = path.canonicalize();
}
"""
    assert descriptions(source) == [
        "std::process::Command",
        "synchronous filesystem metadata",
    ]


def test_flags_std_mutex_lock_but_not_async_lock() -> None:
    source = """
async fn handler(sync_lock: Mutex<u8>, async_lock: tokio::sync::Mutex<u8>) {
    let _a = sync_lock.lock();
    let _b = async_lock.lock().await;
}
"""
    assert descriptions(source) == ["std mutex lock"]


def test_ignores_comments_and_string_literals() -> None:
    source = """
async fn handler() {
    // std::fs::read("a") would block here
    let text = "std::fs::read(\\"a\\")";
    let raw = r#"File::open("a")"#;
    let _ = (text, raw);
}
"""
    assert descriptions(source) == []


def test_ignores_test_module() -> None:
    source = """
#[cfg(test)]
mod tests {
    async fn handler() {
        std::fs::read("a").unwrap();
    }
}
"""
    assert descriptions(source) == []


def test_allow_marker_suppresses_violation() -> None:
    source = """
async fn handler() {
    // blocking-io-allow: startup only
    std::fs::read("a").unwrap();
}
"""
    assert descriptions(source) == []


def test_startup_main_function_is_not_checked() -> None:
    source = """
async fn main() {
    std::fs::read("a").unwrap();
}
"""
    assert descriptions(source) == []


def test_reports_line_numbers() -> None:
    source = 'async fn handler() {\n    let _ = std::fs::read("a");\n}\n'
    violations = checker.check_source("sample.rs", source)
    assert [(item.path, item.line) for item in violations] == [("sample.rs", 2)]


def test_console_server_sources_are_clean() -> None:
    assert checker.main(["--root", str(REPOSITORY_ROOT)]) == 0


def test_main_fails_on_dirty_file(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    dirty = tmp_path / "dirty.rs"
    dirty.write_text('async fn handler() {\n    let _ = std::fs::read("a");\n}\n')
    assert checker.main([str(dirty)]) == 1
    assert "dirty.rs:2" in capsys.readouterr().out
