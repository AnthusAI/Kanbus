use kanbus::cli::run_from_env;
use kanbus::error::KanbusError;

fn run_cli(runner: impl FnOnce() -> Result<(), KanbusError>) -> i32 {
    match runner() {
        Ok(()) => 0,
        Err(error) => match error {
            KanbusError::CommandFailureWithOutput {
                exit_code,
                stdout,
                stderr,
            } => {
                print!("{stdout}");
                eprint!("{stderr}");
                exit_code
            }
            error => {
                eprintln!("{error}");
                match error {
                    KanbusError::CommandFailure { exit_code, .. } => exit_code,
                    _ => 1,
                }
            }
        },
    }
}

fn main() {
    let code = run_cli(run_from_env);
    if code != 0 {
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn run_cli_returns_zero_on_success() {
        assert_eq!(run_cli(|| Ok(())), 0);
    }

    #[test]
    fn run_cli_returns_one_on_error() {
        assert_eq!(
            run_cli(|| Err(KanbusError::IssueOperation("boom".to_string()))),
            1
        );
    }

    #[test]
    fn run_cli_preserves_specific_command_exit_code() {
        assert_eq!(
            run_cli(|| {
                Err(KanbusError::CommandFailure {
                    exit_code: 2,
                    message: "error: missing".to_string(),
                })
            }),
            2
        );
    }
}
