use kanbus::cli::run_from_env;

fn run_cli(runner: impl FnOnce() -> Result<(), String>) -> i32 {
    match runner() {
        Ok(()) => 0,
        Err(error) => {
            eprintln!("{error}");
            1
        }
    }
}

fn main() {
    let code = run_cli(|| run_from_env().map_err(|error| error.to_string()));
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
        assert_eq!(run_cli(|| Err("boom".to_string())), 1);
    }
}
