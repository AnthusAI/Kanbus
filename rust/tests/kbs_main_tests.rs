use std::process::Command;

#[test]
fn kbs_help_exits_zero() {
    let output = Command::new(env!("CARGO_BIN_EXE_kbs"))
        .arg("--help")
        .output()
        .expect("kbs binary should execute");

    assert!(output.status.success());
}

#[test]
fn kbs_invalid_flag_exits_non_zero() {
    let output = Command::new(env!("CARGO_BIN_EXE_kbs"))
        .arg("--definitely-not-a-real-flag")
        .output()
        .expect("kbs binary should execute");

    assert!(!output.status.success());
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(stderr.contains("unexpected argument") || stderr.contains("Usage:"));
}
