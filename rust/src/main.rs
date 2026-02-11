use taskulus::cli::run_from_env;

fn main() {
    if let Err(error) = run_from_env() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
