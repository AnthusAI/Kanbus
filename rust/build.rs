fn main() {
    // Derive the version from git tags so `kbs --version` reports the semantic
    // release version (e.g. "0.11.0" or "0.11.0-31-gd03e59b") instead of the
    // often-stale Cargo.toml version.
    let git_version = std::process::Command::new("git")
        .args(["describe", "--tags", "--always"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.trim().trim_start_matches('v').to_string())
        .unwrap_or_else(|| env!("CARGO_PKG_VERSION").to_string());

    println!("cargo:rustc-env=GIT_VERSION={git_version}");

    // Re-run if HEAD changes (new commits or tags).
    println!("cargo:rerun-if-changed=../.git/HEAD");
    println!("cargo:rerun-if-changed=../.git/refs/tags");

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
