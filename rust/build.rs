fn has_semver_core_prefix(version: &str) -> bool {
    let trimmed = version.trim();
    let mut segments = trimmed.split('.');
    let Some(major) = segments.next() else {
        return false;
    };
    let Some(minor) = segments.next() else {
        return false;
    };
    let Some(patch_with_suffix) = segments.next() else {
        return false;
    };
    let patch = patch_with_suffix
        .chars()
        .take_while(|character| character.is_ascii_digit())
        .collect::<String>();
    !major.is_empty()
        && major.chars().all(|character| character.is_ascii_digit())
        && !minor.is_empty()
        && minor.chars().all(|character| character.is_ascii_digit())
        && !patch.is_empty()
}

fn resolve_git_version() -> String {
    let described = std::process::Command::new("git")
        .args(["describe", "--tags", "--always", "--match", "kanbus-rust-*"])
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .map(|output| output.trim().trim_start_matches("kanbus-rust-").to_string())
        .filter(|version| has_semver_core_prefix(version));
    described.unwrap_or_else(|| env!("CARGO_PKG_VERSION").to_string())
}

fn main() {
    // Derive the version from git tags so `kbs --version` reports the semantic
    // release version (e.g. "0.11.0" or "0.11.0-31-gd03e59b") instead of the
    // often-stale Cargo.toml version. Shallow clones without tags only get a
    // commit hash from git describe; fall back to Cargo.toml in that case.
    let git_version = resolve_git_version();

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
