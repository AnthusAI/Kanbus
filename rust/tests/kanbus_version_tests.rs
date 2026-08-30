use kanbus::kanbus_version::{
    compare_semver_cores, enforce_kanbus_version, format_unparseable_running_version_error,
    parse_semver_core, read_required_kanbus_version, INVALID_KANBUS_VERSION_MESSAGE,
};
use std::fs;
use tempfile::tempdir;

#[test]
fn baked_git_version_has_leading_semver_core() {
    assert!(
        parse_semver_core(env!("GIT_VERSION")).is_some(),
        "GIT_VERSION must have a leading MAJOR.MINOR.PATCH, got {}",
        env!("GIT_VERSION")
    );
}

#[test]
fn compare_semver_cores_table() {
    let cases = [
        ("0.19.1-5-gabc", "0.19.1", true),
        ("0.18.3-29-g36a5204", "0.19.1", false),
        ("0.19.1", "0.19.1", true),
        ("0.20.0", "0.19.1", true),
        ("0.19.0", "0.19.1", false),
        ("0.19.1", "0.19.0", true),
    ];
    for (running, required, expected) in cases {
        assert_eq!(
            compare_semver_cores(running, required),
            expected,
            "running={running} required={required}"
        );
    }
}

#[test]
fn read_required_kanbus_version_missing_file() {
    let temp = tempdir().expect("tempdir");
    assert_eq!(
        read_required_kanbus_version(temp.path()).expect("read version"),
        None
    );
}

#[test]
fn read_required_kanbus_version_invalid_file() {
    let temp = tempdir().expect("tempdir");
    fs::write(temp.path().join("kanbus-version"), "not-a-version\n").expect("write");
    let error = read_required_kanbus_version(temp.path()).expect_err("invalid file");
    assert_eq!(error.message(), INVALID_KANBUS_VERSION_MESSAGE);
}

#[test]
fn enforce_kanbus_version_unparseable_running_version() {
    let temp = tempdir().expect("tempdir");
    fs::write(temp.path().join("kanbus-version"), "1.0.0\n").expect("write");
    let error = enforce_kanbus_version(temp.path(), "release-candidate").expect_err("error");
    assert_eq!(
        error.message(),
        format_unparseable_running_version_error("release-candidate")
    );
}
