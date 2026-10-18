fn main() {
    // Derive the version from git tags so `kbs --version` reports the semantic
    // release version (e.g. "0.11.0" or "0.11.0-31-gd03e59b") instead of the
    // often-stale Cargo.toml version.
    //
    // `git describe --always` prints a short SHA when no matching tag is an
    // ancestor (shallow CI checkouts, crates.io builds without `.git`). The
    // kanbus-version gate needs a leading MAJOR.MINOR.PATCH, so fall back to
    // the package version when describe is not a semver core.
    let pkg_version = env!("CARGO_PKG_VERSION");
    let described = std::process::Command::new("git")
        .args(["describe", "--tags", "--always", "--match", "kanbus-rust-*"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.trim().trim_start_matches("kanbus-rust-").to_string());
    let git_version = described
        .filter(|value| has_leading_semver_core(value))
        .unwrap_or_else(|| pkg_version.to_string());

    println!("cargo:rustc-env=GIT_VERSION={git_version}");

    // Re-run if HEAD changes (new commits or tags).
    println!("cargo:rerun-if-changed=../.git/HEAD");
    println!("cargo:rerun-if-changed=../.git/refs/tags");

    ensure_console_assets_directory_exists();

    // Print post-install instructions when building for release
    if std::env::var("PROFILE").unwrap_or_default() == "release" {
        println!("cargo:warning=");
        println!("cargo:warning=Kanbus installed successfully!");
        println!("cargo:warning=");
        println!("cargo:warning=Optional: Create shortcuts 'kbs' and 'kbsc' by running:");
        println!("cargo:warning=  curl -sSL https://raw.githubusercontent.com/AnthusAI/Kanbus/main/rust/install-aliases.sh | bash");
        println!("cargo:warning=");
    }
}

fn has_leading_semver_core(version: &str) -> bool {
    let core = version
        .trim()
        .split(['-', '+'])
        .next()
        .unwrap_or(version.trim());
    let mut parts = core.split('.');
    let Some(major) = parts.next() else {
        return false;
    };
    let Some(minor) = parts.next() else {
        return false;
    };
    let Some(patch) = parts.next() else {
        return false;
    };
    if parts.next().is_some() {
        return false;
    }
    [major, minor, patch]
        .into_iter()
        .all(|part| !part.is_empty() && part.chars().all(|ch| ch.is_ascii_digit()))
}

const PLACEHOLDER_CONSOLE_INDEX_HTML: &str = "<!doctype html><html><head><title>Kanbus console</title></head><body><h1>Console assets were not built</h1><p>This binary was compiled without the web console bundle. Run <code>make build</code> from the repository root (or <code>rust/tools/sync_console_assets.sh</code>) and rebuild.</p></body></html>\n";

fn ensure_console_assets_directory_exists() {
    println!("cargo:rerun-if-changed=embedded_assets/console");
    let console_index = std::path::Path::new("embedded_assets/console/index.html");
    if console_index.exists() {
        return;
    }
    std::fs::create_dir_all("embedded_assets/console")
        .expect("create embedded_assets/console placeholder directory");
    std::fs::write(console_index, PLACEHOLDER_CONSOLE_INDEX_HTML)
        .expect("write placeholder console index.html");
    println!("cargo:warning=embedded_assets/console was missing; embedded a placeholder page instead of the web console. Run `make build` to bundle the real console UI.");
}
