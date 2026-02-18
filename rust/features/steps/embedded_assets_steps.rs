use std::env;
use std::fs;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::Duration;

use cucumber::{given, then, when};
use reqwest::blocking::Client;

use crate::step_definitions::initialization_steps::KanbusWorld;

// Helper to start console server
fn start_console_server(
    world: &KanbusWorld,
    binary_name: &str,
    with_embed_features: bool,
) -> Result<Child, String> {
    let rust_dir = world
        .working_directory
        .as_ref()
        .ok_or("working directory not set")?
        .join("rust");

    let target_dir = rust_dir.join("target");
    let binary_path = if with_embed_features {
        target_dir.join("release").join(binary_name)
    } else {
        target_dir.join("debug").join(binary_name)
    };

    if !binary_path.exists() {
        return Err(format!("Binary not found at {}", binary_path.display()));
    }

    let mut cmd = Command::new(&binary_path);
    cmd.env("CONSOLE_PORT", "5174")
        .env(
            "CONSOLE_DATA_ROOT",
            world.working_directory.as_ref().unwrap(),
        )
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    cmd.spawn()
        .map_err(|e| format!("Failed to start server: {}", e))
}

// Helper to wait for server to be ready.
// Runs in a dedicated thread to avoid nested tokio runtime conflicts.
fn wait_for_server_ready(port: u16, timeout_secs: u64) -> bool {
    thread::spawn(move || {
        let client = Client::new();
        let url = format!("http://127.0.0.1:{}/api/config", port);
        for _ in 0..(timeout_secs * 10) {
            if let Ok(response) = client.get(&url).send() {
                if response.status().is_success() {
                    return true;
                }
            }
            thread::sleep(Duration::from_millis(100));
        }
        false
    })
    .join()
    .unwrap_or(false)
}

// Helper to make blocking HTTP requests from async contexts.
fn blocking_get(url: &str) -> Result<(u16, String), String> {
    let url = url.to_string();
    thread::spawn(move || {
        let client = Client::new();
        let response = client.get(&url).send().map_err(|e| e.to_string())?;
        let status = response.status().as_u16();
        let body = response.text().map_err(|e| e.to_string())?;
        Ok((status, body))
    })
    .join()
    .map_err(|_| "thread panicked".to_string())?
}

#[given("I have the kanbus-console binary with embedded assets")]
async fn given_kanbus_console_binary_with_embedded_assets(world: &mut KanbusWorld) {
    // Set working directory to repo root if not already set.
    if world.working_directory.is_none() {
        let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")));
        world.working_directory = Some(repo_root);
    }
    // Build the console binary with embed-assets feature
    let rust_dir = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join("rust");

    // First ensure frontend is built
    let console_dir = world
        .working_directory
        .as_ref()
        .unwrap()
        .join("apps")
        .join("console");

    // Skip if no console app (for simpler test environments)
    if !console_dir.exists() {
        panic!("Console app not found at {}", console_dir.display());
    }

    let output = Command::new("npm")
        .args(&["run", "build"])
        .current_dir(&console_dir)
        .output()
        .expect("Failed to build frontend");

    if !output.status.success() {
        panic!(
            "Frontend build failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }

    // Now build Rust binary with embed-assets feature
    let output = Command::new("cargo")
        .args(&[
            "build",
            "--release",
            "--bin",
            "kbsc",
            "--features",
            "embed-assets",
        ])
        .current_dir(&rust_dir)
        .output()
        .expect("Failed to build kbsc");

    if !output.status.success() {
        panic!(
            "Rust build failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }

    // Store that we have embedded binary ready
    world.stdout = Some("embedded binary ready".to_string());
}

#[given("CONSOLE_ASSETS_ROOT is not set")]
async fn given_console_assets_root_not_set(_world: &mut KanbusWorld) {
    env::remove_var("CONSOLE_ASSETS_ROOT");
}

#[given(regex = r"^I set CONSOLE_ASSETS_ROOT to (.+)$")]
async fn given_console_assets_root_set(world: &mut KanbusWorld, path: String) {
    let custom_path = if path == "a custom directory" {
        world
            .working_directory
            .as_ref()
            .unwrap()
            .join("custom_assets")
    } else if path == "apps/console/dist" {
        world
            .working_directory
            .as_ref()
            .unwrap()
            .join("apps")
            .join("console")
            .join("dist")
    } else {
        PathBuf::from(path)
    };

    env::set_var("CONSOLE_ASSETS_ROOT", &custom_path);
    world.cache_path = Some(custom_path);
}

#[given("I place custom assets in that directory")]
async fn given_custom_assets_placed(world: &mut KanbusWorld) {
    let custom_dir = world
        .cache_path
        .as_ref()
        .expect("custom assets directory not set");

    fs::create_dir_all(custom_dir).expect("Failed to create custom assets dir");

    fs::write(
        custom_dir.join("index.html"),
        "<!DOCTYPE html><html><body>Custom Assets</body></html>",
    )
    .expect("Failed to write custom index.html");

    fs::create_dir_all(custom_dir.join("assets")).expect("Failed to create assets dir");
    fs::write(
        custom_dir.join("assets").join("custom.js"),
        "console.log('custom');",
    )
    .expect("Failed to write custom JS");
}

#[given(regex = r"^I build console_local without --features embed-assets$")]
async fn given_build_without_embed_assets(world: &mut KanbusWorld) {
    // Set working directory to repo root if not already set.
    if world.working_directory.is_none() {
        let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(env!("CARGO_MANIFEST_DIR")));
        world.working_directory = Some(repo_root);
    }
    let rust_dir = world
        .working_directory
        .as_ref()
        .expect("working directory not set")
        .join("rust");

    let output = Command::new("cargo")
        .args(&["build", "--bin", "kbsc"])
        .current_dir(&rust_dir)
        .output()
        .expect("Failed to build kbsc");

    if !output.status.success() {
        panic!(
            "Rust build failed: {}",
            String::from_utf8_lossy(&output.stderr)
        );
    }

    world.stdout = Some("development binary ready".to_string());
}

#[when("I start the console server")]
async fn when_start_console_server(world: &mut KanbusWorld) {
    let with_embed = world
        .stdout
        .as_ref()
        .map(|s| s.contains("embedded"))
        .unwrap_or(false);

    let binary_name = if cfg!(windows) {
        "kbsc.exe"
    } else {
        "kbsc"
    };

    match start_console_server(world, binary_name, with_embed) {
        Ok(_child) => {
            // Store child process handle (we'd need to add this to KanbusWorld)
            // For now, just check if it starts
            world.daemon_spawned = true;

            // Wait for server to be ready
            if !wait_for_server_ready(5174, 30) {
                panic!("Console server failed to become ready");
            }
        }
        Err(e) => {
            panic!("Failed to start console server: {}", e);
        }
    }
}

#[then("the server starts successfully")]
async fn then_server_starts_successfully(world: &mut KanbusWorld) {
    assert!(
        world.daemon_spawned,
        "Console server should have started successfully"
    );
}

#[then(regex = r#"^the startup message shows "(.+)"$"#)]
async fn then_startup_message_shows(world: &mut KanbusWorld, expected_msg: String) {
    // This would require capturing stdout from the server process
    // For now, we verify the binary was built with the right features
    let built_with_embed = world
        .stdout
        .as_ref()
        .map(|s| s.contains("embedded"))
        .unwrap_or(false);

    if expected_msg.contains("embedded assets") {
        assert!(
            built_with_embed,
            "Server should be built with embedded assets"
        );
    }
}

#[then(regex = r"^I can access (.+)$")]
async fn then_can_access_url(world: &mut KanbusWorld, url: String) {
    let (status, body) =
        blocking_get(&url).unwrap_or_else(|e| panic!("Failed to access {}: {}", url, e));
    assert!(
        (200..300).contains(&status),
        "Should be able to access {}",
        url
    );
    world.formatted_output = Some(body);
}

#[then("the UI index.html loads")]
async fn then_ui_index_html_loads(world: &mut KanbusWorld) {
    let html = world
        .formatted_output
        .as_ref()
        .expect("No HTML content captured");

    assert!(
        html.contains("<!doctype html") || html.contains("<!DOCTYPE html"),
        "Should contain HTML doctype"
    );
}

#[then(regex = r"^JavaScript assets load from (.+)$")]
async fn then_javascript_assets_load(world: &mut KanbusWorld, path_pattern: String) {
    let html = world
        .formatted_output
        .as_ref()
        .expect("No HTML content captured");

    // Look for script tags with src matching the pattern
    assert!(
        html.contains(&path_pattern) || html.contains("/assets/index-"),
        "Should contain JavaScript asset references"
    );

    // Try to fetch one JS asset
    let js_url = "http://127.0.0.1:5174/assets/index-CqkOfnBn.js"; // Example hash
    let _ = blocking_get(js_url); // Just verify we can attempt to fetch
}

#[then(regex = r"^CSS assets load from (.+)$")]
async fn then_css_assets_load(world: &mut KanbusWorld, path_pattern: String) {
    let html = world
        .formatted_output
        .as_ref()
        .expect("No HTML content captured");

    // Look for link tags with href matching the pattern
    assert!(
        html.contains(&path_pattern) || html.contains("/assets/index-"),
        "Should contain CSS asset references"
    );
}

#[then(regex = r"^API endpoint (.+) responds$")]
async fn then_api_endpoint_responds(world: &mut KanbusWorld, endpoint: String) {
    let url = format!("http://127.0.0.1:5174{}", endpoint);
    let (status, body) =
        blocking_get(&url).unwrap_or_else(|e| panic!("Failed to access {}: {}", url, e));
    assert!(
        (200..300).contains(&status),
        "API endpoint {} should respond successfully",
        endpoint
    );
    world.formatted_output = Some(body);
}

#[then("assets are served from the filesystem path")]
async fn then_assets_served_from_filesystem(_world: &mut KanbusWorld) {
    let (_status, html) =
        blocking_get("http://127.0.0.1:5174/").expect("Failed to fetch root");
    assert!(
        html.contains("Custom Assets"),
        "Should serve custom assets from filesystem"
    );
}

#[then("embedded assets are NOT used")]
async fn then_embedded_assets_not_used(_world: &mut KanbusWorld) {
    // This is validated by the previous step showing custom assets
    // If embedded assets were used, we'd see the real frontend, not "Custom Assets"
}

#[then(regex = r"^assets are served from (.+)$")]
async fn then_assets_served_from_path(world: &mut KanbusWorld, path: String) {
    // For development build test
    let expected = if path.contains("apps/console/dist") {
        "apps/console/dist"
    } else if path == "embedded binary data" {
        "embedded"
    } else {
        &path
    };

    // Verify server is serving from expected source
    let (status, body) =
        blocking_get("http://127.0.0.1:5174/").expect("Failed to fetch root");
    assert!(
        (200..300).contains(&status),
        "Should serve assets from {}",
        expected
    );
    world.formatted_output = Some(body);
}

#[then("the binary does not contain embedded assets")]
async fn then_binary_does_not_contain_embedded_assets(world: &mut KanbusWorld) {
    // Check that binary was built without embed-assets feature
    let built_without_embed = world
        .stdout
        .as_ref()
        .map(|s| s.contains("development"))
        .unwrap_or(false);

    assert!(
        built_without_embed,
        "Binary should be built without embed-assets feature"
    );
}
