use std::path::PathBuf;
use std::process::Command;

use cucumber::then;

use kanbus::file_io::load_project_directory;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

#[then("project/issues should be committed to git")]
fn then_project_issues_committed_to_git(world: &mut KanbusWorld) {
    let cwd = world.working_directory.as_ref().expect("cwd");
    let cwd = cwd.canonicalize().unwrap_or_else(|_| cwd.clone());
    let project_dir = load_project_dir(world);
    let issues_path = project_dir.join("issues");
    let issues_path = issues_path.canonicalize().unwrap_or(issues_path);
    let relative_issues_path = issues_path
        .strip_prefix(&cwd)
        .expect("issues path under repo root")
        .to_string_lossy()
        .replace('\\', "/");

    let output = Command::new("git")
        .args(["status", "--porcelain", "--", &relative_issues_path])
        .current_dir(&cwd)
        .output()
        .expect("git status");

    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(stdout.trim().is_empty(), "{stdout}");
}
