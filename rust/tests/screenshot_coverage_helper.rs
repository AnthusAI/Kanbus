use std::fs;
use std::path::PathBuf;
use std::process::Command;

use kanbus::cli::run_from_args_with_output;
use kanbus::console_screenshot::capture_console_screenshot;
use kanbus::file_io::initialize_project;
use tempfile::TempDir;

fn env_flag(name: &str) -> bool {
    std::env::var(name)
        .ok()
        .map(|value| {
            let normalized = value.trim().to_ascii_lowercase();
            matches!(normalized.as_str(), "1" | "true" | "yes" | "on")
        })
        .unwrap_or(false)
}

#[test]
fn screenshot_coverage_helper() {
    if !env_flag("KANBUS_ENABLE_COVERAGE_HELPER") {
        return;
    }

    let temp_dir = TempDir::new().expect("tempdir");
    let root = temp_dir.path().join("repo");
    fs::create_dir_all(&root).expect("create repo");
    Command::new("git")
        .args(["init"])
        .current_dir(&root)
        .output()
        .expect("git init");
    initialize_project(&root, false).expect("initialize project");
    fs::write(root.join(".kanbus.yml"), "console_port: 65520\n").expect("write console port");

    std::env::set_var("KANBUS_NO_DAEMON", "1");
    std::env::set_var("KANBUS_TEST_SCREENSHOT_ASSUME_SERVER", "1");

    std::env::set_var("KANBUS_TEST_SCREENSHOT_MOCK", "success");
    let _ = capture_console_screenshot(&root, None, None, None, false, vec![], vec![]);
    let _ = capture_console_screenshot(
        &root,
        Some("coverage-dark.png".to_string()),
        Some("dark".to_string()),
        Some("issues".to_string()),
        true,
        vec!["backlog".to_string()],
        vec!["in_progress".to_string()],
    );

    std::env::set_var("KANBUS_TEST_SCREENSHOT_MOCK", "unavailable");
    let _ = capture_console_screenshot(&root, None, None, None, false, vec![], vec![]);

    let _ = capture_console_screenshot(
        &root,
        None,
        Some("sepia".to_string()),
        None,
        false,
        vec![],
        vec![],
    );
    let _ = capture_console_screenshot(
        &root,
        None,
        None,
        Some("pods".to_string()),
        false,
        vec![],
        vec![],
    );

    std::env::remove_var("KANBUS_TEST_SCREENSHOT_MOCK");
    std::env::set_var("KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING", "1");
    let _ = capture_console_screenshot(&root, None, None, None, false, vec![], vec![]);

    let fake_node = root.join("fake-node.sh");
    fs::write(
        &fake_node,
        "#!/bin/sh\nprintf 'playwright browser missing\\n' >&2\nexit 1\n",
    )
    .expect("write fake node");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = fs::metadata(&fake_node).expect("metadata").permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&fake_node, permissions).expect("chmod");
    }
    std::env::remove_var("KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING");
    std::env::set_var("KANBUS_TEST_SCREENSHOT_NODE_EXECUTABLE", &fake_node);
    let _ = capture_console_screenshot(&root, None, None, None, false, vec![], vec![]);

    fs::write(
        &fake_node,
        "#!/bin/sh\nprintf 'capture harness exploded\\n' >&2\nexit 1\n",
    )
    .expect("write generic fake node");
    let _ = capture_console_screenshot(&root, None, None, None, false, vec![], vec![]);

    fs::write(
        &fake_node,
        "#!/bin/sh\nprintf '\\211PNG\\r\\n\\032\\n' > \"$3\"\nexit 0\n",
    )
    .expect("write success fake node");
    let _ = capture_console_screenshot(
        &root,
        Some("coverage-board.png".to_string()),
        None,
        None,
        false,
        vec![],
        vec![],
    );

    let search_root = root.join("custom-script-root");
    let script_dir = search_root.join("scripts");
    fs::create_dir_all(&script_dir).expect("create script dir");
    let manifest_script = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(|parent| {
            parent
                .join("scripts")
                .join("capture_console_screenshot.mjs")
        })
        .expect("manifest parent");
    fs::copy(
        manifest_script,
        script_dir.join("capture_console_screenshot.mjs"),
    )
    .expect("copy capture script");
    std::env::remove_var("KANBUS_TEST_SCREENSHOT_NODE_EXECUTABLE");
    std::env::set_var("KANBUS_TEST_SCREENSHOT_MOCK", "success");
    std::env::set_var(
        "KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT",
        search_root.to_string_lossy().as_ref(),
    );
    let _ = capture_console_screenshot(&root, None, None, None, false, vec![], vec![]);

    let empty_root = root.join("empty-script-root");
    fs::create_dir_all(&empty_root).expect("create empty root");
    std::env::remove_var("KANBUS_TEST_SCREENSHOT_MOCK");
    std::env::set_var(
        "KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT",
        empty_root.to_string_lossy().as_ref(),
    );
    std::env::set_var("KANBUS_TEST_SCREENSHOT_HIDE_PACKAGE_SCRIPT", "1");
    let _ = capture_console_screenshot(&root, None, None, None, false, vec![], vec![]);

    let run_cli = |root: &std::path::Path, args: Vec<&str>| {
        let root = root.to_path_buf();
        let args: Vec<String> = args.into_iter().map(str::to_string).collect();
        let _ = std::thread::spawn(move || run_from_args_with_output(args, &root)).join();
    };

    std::env::set_var("KANBUS_TEST_SCREENSHOT_ASSUME_SERVER", "1");
    std::env::set_var("KANBUS_TEST_SCREENSHOT_MOCK", "success");
    run_cli(
        &root,
        vec![
            "kanbus",
            "console",
            "screenshot",
            "--mode",
            "dark",
            "--view",
            "all",
        ],
    );
    run_cli(
        &root,
        vec![
            "kanbus",
            "console",
            "screenshot",
            "--expand",
            "backlog",
            "--collapse",
            "in_progress",
        ],
    );

    std::env::remove_var("KANBUS_TEST_SCREENSHOT_ASSUME_SERVER");
    std::env::remove_var("KANBUS_TEST_SCREENSHOT_MOCK");
    std::env::remove_var("KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING");
    std::env::remove_var("KANBUS_TEST_SCREENSHOT_NODE_EXECUTABLE");
    std::env::remove_var("KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT");
    std::env::remove_var("KANBUS_TEST_SCREENSHOT_HIDE_PACKAGE_SCRIPT");
    std::env::remove_var("KANBUS_TEST_SCREENSHOT_LAST_MODE");
    std::env::remove_var("KANBUS_TEST_SCREENSHOT_CAPTURE_OPTIONS");
    std::env::remove_var("KANBUS_TEST_SCREENSHOT_PREREQUISITES_VERIFIED");
}
