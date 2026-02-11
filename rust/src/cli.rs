//! CLI command definitions.

use std::ffi::OsString;
use std::path::Path;

use clap::{Parser, Subcommand};

use crate::daemon_client::{request_shutdown, request_status};
use crate::daemon_server::run_daemon;
use crate::error::TaskulusError;
use crate::file_io::{ensure_git_repository, initialize_project, resolve_root};
use crate::issue_close::close_issue;
use crate::issue_comment::add_comment;
use crate::issue_creation::{create_issue, IssueCreationRequest};
use crate::issue_delete::delete_issue;
use crate::issue_display::format_issue_for_display;
use crate::issue_listing::list_issues;
use crate::issue_lookup::load_issue_from_project;
use crate::issue_update::update_issue;
use crate::migration::migrate_from_beads;
use crate::users::get_current_user;

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
    /// Create a new issue.
    Create {
        /// Issue title.
        #[arg(required = true)]
        title: Vec<String>,
        /// Issue type override.
        #[arg(long = "type", value_name = "TYPE")]
        issue_type: Option<String>,
        /// Issue priority override.
        #[arg(long)]
        priority: Option<u8>,
        /// Issue assignee.
        #[arg(long)]
        assignee: Option<String>,
        /// Parent issue identifier.
        #[arg(long)]
        parent: Option<String>,
        /// Issue labels.
        #[arg(long)]
        label: Vec<String>,
        /// Issue description.
        #[arg(long, num_args = 1..)]
        description: Option<Vec<String>>,
    },
    /// Show an issue.
    Show {
        /// Issue identifier.
        identifier: String,
        /// Emit JSON output.
        #[arg(long)]
        json: bool,
    },
    /// Update an issue.
    Update {
        /// Issue identifier.
        identifier: String,
        /// Updated title.
        #[arg(long, num_args = 1..)]
        title: Option<Vec<String>>,
        /// Updated description.
        #[arg(long, num_args = 1..)]
        description: Option<Vec<String>>,
        /// Updated status.
        #[arg(long)]
        status: Option<String>,
    },
    /// Close an issue.
    Close {
        /// Issue identifier.
        identifier: String,
    },
    /// Delete an issue.
    Delete {
        /// Issue identifier.
        identifier: String,
    },
    /// Add a comment to an issue.
    Comment {
        /// Issue identifier.
        identifier: String,
        /// Comment text.
        #[arg(required = true)]
        text: Vec<String>,
    },
    /// List issues.
    List,
    /// Migrate Beads issues into Taskulus.
    Migrate,
    /// Run the daemon server.
    Daemon {
        /// Repository root path.
        #[arg(long)]
        root: String,
    },
    /// Report daemon status.
    #[command(name = "daemon-status")]
    DaemonStatus,
    /// Stop the daemon process.
    #[command(name = "daemon-stop")]
    DaemonStop,
}

/// Output produced by a CLI command.
#[derive(Debug, Default)]
pub struct CommandOutput {
    pub stdout: String,
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
    let output = run_from_args_with_output(args, cwd)?;
    if !output.stdout.is_empty() {
        println!("{}", output.stdout);
    }
    Ok(())
}

/// Run the CLI with explicit arguments and capture stdout output.
///
/// # Arguments
///
/// * `args` - Command line arguments.
/// * `cwd` - Working directory for the command.
///
/// # Errors
///
/// Returns `TaskulusError` if execution fails.
pub fn run_from_args_with_output<I, T>(args: I, cwd: &Path) -> Result<CommandOutput, TaskulusError>
where
    I: IntoIterator<Item = T>,
    T: Into<OsString> + Clone,
{
    let cli = Cli::parse_from(args);
    let root = resolve_root(cwd);
    let stdout = execute_command(cli.command, &root)?;

    Ok(CommandOutput {
        stdout: stdout.unwrap_or_default(),
    })
}

fn execute_command(command: Commands, root: &Path) -> Result<Option<String>, TaskulusError> {
    match command {
        Commands::Init { dir } => {
            ensure_git_repository(root)?;
            initialize_project(root, &dir)?;
            Ok(None)
        }
        Commands::Create {
            title,
            issue_type,
            priority,
            assignee,
            parent,
            label,
            description,
        } => {
            let title_text = title.join(" ");
            if title_text.trim().is_empty() {
                return Err(TaskulusError::IssueOperation(
                    "title is required".to_string(),
                ));
            }
            let description_text = description
                .as_ref()
                .map(|values| values.join(" "))
                .unwrap_or_default();
            let request = IssueCreationRequest {
                root: root.to_path_buf(),
                title: title_text,
                issue_type,
                priority,
                assignee,
                parent,
                labels: label,
                description: if description_text.is_empty() {
                    None
                } else {
                    Some(description_text)
                },
            };
            let issue = create_issue(&request)?;
            Ok(Some(issue.identifier))
        }
        Commands::Show { identifier, json } => {
            let lookup = load_issue_from_project(root, &identifier)?;
            if json {
                let payload = serde_json::to_string_pretty(&lookup.issue)
                    .map_err(|error| TaskulusError::Io(error.to_string()))?;
                return Ok(Some(payload));
            }
            Ok(Some(format_issue_for_display(&lookup.issue)))
        }
        Commands::Update {
            identifier,
            title,
            description,
            status,
        } => {
            let title_text = title
                .as_ref()
                .map(|values| values.join(" "))
                .unwrap_or_default();
            let description_text = description
                .as_ref()
                .map(|values| values.join(" "))
                .unwrap_or_default();
            update_issue(
                root,
                &identifier,
                if title_text.is_empty() {
                    None
                } else {
                    Some(title_text.as_str())
                },
                if description_text.is_empty() {
                    None
                } else {
                    Some(description_text.as_str())
                },
                status.as_deref(),
            )?;
            Ok(None)
        }
        Commands::Close { identifier } => {
            close_issue(root, &identifier)?;
            Ok(None)
        }
        Commands::Delete { identifier } => {
            delete_issue(root, &identifier)?;
            Ok(None)
        }
        Commands::Comment { identifier, text } => {
            let text_value = text.join(" ");
            add_comment(root, &identifier, &get_current_user(), &text_value)?;
            Ok(None)
        }
        Commands::List => {
            let issues = list_issues(root)?;
            let mut lines = Vec::new();
            for issue in issues {
                lines.push(format!("{} {}", issue.identifier, issue.title));
            }
            Ok(Some(lines.join("\n")))
        }
        Commands::Migrate => {
            let result = migrate_from_beads(root)?;
            Ok(Some(format!("migrated {} issues", result.issue_count)))
        }
        Commands::Daemon { root } => {
            run_daemon(Path::new(&root))?;
            Ok(None)
        }
        Commands::DaemonStatus => {
            let status = request_status(root)?;
            let payload = serde_json::to_string_pretty(&status)
                .map_err(|error| TaskulusError::Io(error.to_string()))?;
            Ok(Some(payload))
        }
        Commands::DaemonStop => {
            let status = request_shutdown(root)?;
            let payload = serde_json::to_string_pretty(&status)
                .map_err(|error| TaskulusError::Io(error.to_string()))?;
            Ok(Some(payload))
        }
    }
}

/// Run the CLI using process arguments and current directory.
///
/// # Errors
///
/// Returns `TaskulusError` if execution fails.
pub fn run_from_env() -> Result<(), TaskulusError> {
    run_from_args(std::env::args_os(), Path::new("."))
}
