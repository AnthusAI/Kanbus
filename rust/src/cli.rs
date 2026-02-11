//! CLI command definitions.

use std::ffi::OsString;
use std::path::Path;

use clap::{Parser, Subcommand};

use crate::error::TaskulusError;
use crate::file_io::{ensure_git_repository, initialize_project, resolve_root};

/// Taskulus CLI arguments.
#[derive(Debug, Parser)]
#[command(name = "tsk")]
pub struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Debug, Subcommand)]
enum Commands {
    /// Initialize a Taskulus project in the current repository.
    Init {
        /// Project directory name.
        #[arg(long, default_value = "project")]
        dir: String,
    },
}

/// Run the CLI with explicit arguments.
///
/// # Arguments
///
/// * `args` - Command line arguments.
/// * `cwd` - Working directory for the command.
///
/// # Errors
///
/// Returns `TaskulusError` if execution fails.
pub fn run_from_args<I, T>(args: I, cwd: &Path) -> Result<(), TaskulusError>
where
    I: IntoIterator<Item = T>,
    T: Into<OsString> + Clone,
{
    let cli = Cli::parse_from(args);
    let root = resolve_root(cwd);

    match cli.command {
        Commands::Init { dir } => {
            ensure_git_repository(&root)?;
            initialize_project(&root, &dir)?;
        }
    }

    Ok(())
}

/// Run the CLI using process arguments and current directory.
///
/// # Errors
///
/// Returns `TaskulusError` if execution fails.
pub fn run_from_env() -> Result<(), TaskulusError> {
    run_from_args(std::env::args_os(), Path::new("."))
}
