//! CLI command definitions.

use std::ffi::OsString;
use std::path::Path;

use clap::error::ErrorKind;
use clap::{Parser, Subcommand};

use crate::daemon_client::{request_shutdown, request_status};
use crate::daemon_server::run_daemon;
use crate::dependencies::{add_dependency, list_ready_issues, remove_dependency};
use crate::dependency_tree::{build_dependency_tree, render_dependency_tree};
use crate::doctor::run_doctor;
use crate::error::TaskulusError;
use crate::file_io::{ensure_git_repository, initialize_project, resolve_root};
use crate::issue_close::close_issue;
use crate::issue_comment::add_comment;
use crate::issue_creation::{create_issue, IssueCreationRequest};
use crate::issue_delete::delete_issue;
use crate::issue_display::format_issue_for_display;
use crate::issue_listing::list_issues;
use crate::issue_lookup::load_issue_from_project;
use crate::issue_transfer::{localize_issue, promote_issue};
use crate::issue_update::update_issue;
use crate::maintenance::{collect_project_stats, validate_project};
use crate::migration::{load_beads_issue_by_id, load_beads_issues, migrate_from_beads};
use crate::models::IssueData;
use crate::queries::{filter_issues, search_issues, sort_issues};
use crate::users::get_current_user;
use crate::wiki::{render_wiki_page, WikiRenderRequest};

/// Taskulus CLI arguments.
#[derive(Debug, Parser)]
#[command(name = "tsk", version)]
pub struct Cli {
    /// Enable Beads compatibility mode (read .beads/issues.jsonl).
    #[arg(long)]
    beads: bool,
    #[command(subcommand)]
    command: Commands,
}

#[derive(Debug, Subcommand)]
enum Commands {
    /// Initialize a Taskulus project in the current repository.
    Init {
        /// Create project-local alongside project.
        #[arg(long)]
        local: bool,
    },
    /// Create a new issue.
    Create {
        /// Issue title.
        #[arg(num_args = 0.., value_name = "TITLE")]
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
        /// Create the issue in project-local.
        #[arg(long)]
        local: bool,
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
        /// Claim the issue.
        #[arg(long)]
        claim: bool,
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
    List {
        /// Status filter.
        #[arg(long)]
        status: Option<String>,
        /// Type filter.
        #[arg(long = "type")]
        issue_type: Option<String>,
        /// Assignee filter.
        #[arg(long)]
        assignee: Option<String>,
        /// Label filter.
        #[arg(long)]
        label: Option<String>,
        /// Sort key.
        #[arg(long)]
        sort: Option<String>,
        /// Search term.
        #[arg(long)]
        search: Option<String>,
        /// Exclude local issues.
        #[arg(long = "no-local")]
        no_local: bool,
        /// Show only local issues.
        #[arg(long = "local-only")]
        local_only: bool,
    },
    /// Validate project integrity.
    Validate,
    /// Promote a local issue to shared.
    Promote {
        /// Issue identifier.
        identifier: String,
    },
    /// Move a shared issue to project-local.
    Localize {
        /// Issue identifier.
        identifier: String,
    },
    /// Report project statistics.
    Stats,
    /// Manage issue dependencies.
    Dep {
        #[command(subcommand)]
        command: DependencyCommands,
    },
    /// List issues that are ready (not blocked).
    Ready {
        /// Exclude local issues.
        #[arg(long = "no-local")]
        no_local: bool,
        /// Show only local issues.
        #[arg(long = "local-only")]
        local_only: bool,
    },
    /// Migrate Beads issues into Taskulus.
    Migrate,
    /// Run environment diagnostics.
    Doctor,
    /// Run the daemon server.
    Daemon {
        /// Repository root path.
        #[arg(long)]
        root: String,
    },
    /// Manage wiki pages.
    Wiki {
        #[command(subcommand)]
        command: WikiCommands,
    },
    /// Report daemon status.
    #[command(name = "daemon-status")]
    DaemonStatus,
    /// Stop the daemon process.
    #[command(name = "daemon-stop")]
    DaemonStop,
}

#[derive(Debug, Subcommand)]
enum DependencyCommands {
    /// Add a dependency to an issue.
    Add {
        /// Issue identifier.
        identifier: String,
        /// Blocked-by dependency target.
        #[arg(long = "blocked-by")]
        blocked_by: Option<String>,
        /// Relates-to dependency target.
        #[arg(long = "relates-to")]
        relates_to: Option<String>,
    },
    /// Remove a dependency from an issue.
    Remove {
        /// Issue identifier.
        identifier: String,
        /// Blocked-by dependency target.
        #[arg(long = "blocked-by")]
        blocked_by: Option<String>,
        /// Relates-to dependency target.
        #[arg(long = "relates-to")]
        relates_to: Option<String>,
    },
    /// Display dependency tree.
    Tree {
        /// Issue identifier.
        identifier: String,
        /// Optional depth limit.
        #[arg(long)]
        depth: Option<usize>,
        /// Output format (text, json, dot).
        #[arg(long, default_value = "text")]
        format: String,
    },
}

#[derive(Debug, Subcommand)]
enum WikiCommands {
    /// Render a wiki page.
    Render {
        /// Wiki page path.
        page: String,
    },
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
    let cli = match Cli::try_parse_from(args) {
        Ok(parsed) => parsed,
        Err(error) => {
            let rendered = error.render().to_string();
            if matches!(
                error.kind(),
                ErrorKind::DisplayHelp
                    | ErrorKind::DisplayHelpOnMissingArgumentOrSubcommand
                    | ErrorKind::DisplayVersion
            ) {
                return Ok(CommandOutput { stdout: rendered });
            }
            return Err(TaskulusError::IssueOperation(rendered));
        }
    };
    let root = resolve_root(cwd);
    let stdout = execute_command(cli.command, &root, cli.beads)?;

    Ok(CommandOutput {
        stdout: stdout.unwrap_or_default(),
    })
}

fn execute_command(
    command: Commands,
    root: &Path,
    beads_mode: bool,
) -> Result<Option<String>, TaskulusError> {
    match command {
        Commands::Init { local } => {
            ensure_git_repository(root)?;
            initialize_project(root, local)?;
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
            local,
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
                local,
            };
            let issue = create_issue(&request)?;
            Ok(Some(issue.identifier))
        }
        Commands::Show { identifier, json } => {
            let issue = if beads_mode {
                load_beads_issue_by_id(root, &identifier)?
            } else {
                load_issue_from_project(root, &identifier)?.issue
            };
            if json {
                let payload =
                    serde_json::to_string_pretty(&issue).expect("failed to serialize issue");
                return Ok(Some(payload));
            }
            Ok(Some(format_issue_for_display(&issue)))
        }
        Commands::Update {
            identifier,
            title,
            description,
            status,
            claim,
        } => {
            let title_text = title
                .as_ref()
                .map(|values| values.join(" "))
                .unwrap_or_default();
            let description_text = description
                .as_ref()
                .map(|values| values.join(" "))
                .unwrap_or_default();
            let assignee_value = if claim {
                Some(get_current_user())
            } else {
                None
            };
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
                assignee_value.as_deref(),
                claim,
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
        Commands::Promote { identifier } => {
            promote_issue(root, &identifier)?;
            Ok(None)
        }
        Commands::Localize { identifier } => {
            localize_issue(root, &identifier)?;
            Ok(None)
        }
        Commands::List {
            status,
            issue_type,
            assignee,
            label,
            sort,
            search,
            no_local,
            local_only,
        } => {
            let issues = if beads_mode {
                if local_only || no_local {
                    return Err(TaskulusError::IssueOperation(
                        "beads mode does not support local filtering".to_string(),
                    ));
                }
                let issues = load_beads_issues(root)?;
                let filtered = filter_issues(
                    issues,
                    status.as_deref(),
                    issue_type.as_deref(),
                    assignee.as_deref(),
                    label.as_deref(),
                );
                let searched = search_issues(filtered, search.as_deref());
                sort_issues(searched, sort.as_deref())?
            } else {
                list_issues(
                    root,
                    status.as_deref(),
                    issue_type.as_deref(),
                    assignee.as_deref(),
                    label.as_deref(),
                    sort.as_deref(),
                    search.as_deref(),
                    !no_local,
                    local_only,
                )?
            };
            let mut lines = Vec::new();
            for issue in issues {
                lines.push(format_issue_line(&issue));
            }
            Ok(Some(lines.join("\n")))
        }
        Commands::Validate => {
            validate_project(root)?;
            Ok(None)
        }
        Commands::Stats => {
            let stats = collect_project_stats(root)?;
            let mut lines = Vec::new();
            lines.push(format!("total issues: {}", stats.total));
            lines.push(format!("open issues: {}", stats.open_count));
            lines.push(format!("closed issues: {}", stats.closed_count));
            for (issue_type, count) in stats.type_counts {
                lines.push(format!("type: {issue_type}: {count}"));
            }
            Ok(Some(lines.join("\n")))
        }
        Commands::Dep { command } => match command {
            DependencyCommands::Add {
                identifier,
                blocked_by,
                relates_to,
            } => {
                let (target_id, dependency_type) = match (blocked_by, relates_to) {
                    (Some(value), _) => (value, "blocked-by"),
                    (None, Some(value)) => (value, "relates-to"),
                    (None, None) => {
                        return Err(TaskulusError::IssueOperation(
                            "dependency target is required".to_string(),
                        ));
                    }
                };
                add_dependency(root, &identifier, &target_id, dependency_type)?;
                Ok(None)
            }
            DependencyCommands::Remove {
                identifier,
                blocked_by,
                relates_to,
            } => {
                let (target_id, dependency_type) = match (blocked_by, relates_to) {
                    (Some(value), _) => (value, "blocked-by"),
                    (None, Some(value)) => (value, "relates-to"),
                    (None, None) => {
                        return Err(TaskulusError::IssueOperation(
                            "dependency target is required".to_string(),
                        ));
                    }
                };
                remove_dependency(root, &identifier, &target_id, dependency_type)?;
                Ok(None)
            }
            DependencyCommands::Tree {
                identifier,
                depth,
                format,
            } => {
                let tree = build_dependency_tree(root, &identifier, depth)?;
                let output = render_dependency_tree(&tree, &format, None)?;
                Ok(Some(output))
            }
        },
        Commands::Ready {
            no_local,
            local_only,
        } => {
            let issues = if beads_mode {
                if local_only || no_local {
                    return Err(TaskulusError::IssueOperation(
                        "beads mode does not support local filtering".to_string(),
                    ));
                }
                load_beads_issues(root)?
                    .into_iter()
                    .filter(|issue| issue.status != "closed" && !is_issue_blocked(issue))
                    .collect()
            } else {
                list_ready_issues(root, !no_local, local_only)?
            };
            let mut lines = Vec::new();
            for issue in issues {
                lines.push(format_ready_line(&issue));
            }
            Ok(Some(lines.join("\n")))
        }
        Commands::Migrate => {
            let result = migrate_from_beads(root)?;
            Ok(Some(format!("migrated {} issues", result.issue_count)))
        }
        Commands::Doctor => {
            let result = run_doctor(root)?;
            Ok(Some(format!("ok {}", result.project_dir.display())))
        }
        Commands::Daemon { root } => {
            run_daemon(Path::new(&root))?;
            Ok(None)
        }
        Commands::Wiki { command } => match command {
            WikiCommands::Render { page } => {
                let request = WikiRenderRequest {
                    root: root.to_path_buf(),
                    page_path: Path::new(&page).to_path_buf(),
                };
                let output = render_wiki_page(&request)?;
                Ok(Some(output))
            }
        },
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

fn format_issue_line(issue: &IssueData) -> String {
    let prefix = issue
        .custom
        .get("project_path")
        .and_then(|value| value.as_str())
        .map(|value| format!("{value} "))
        .unwrap_or_default();
    format!("{prefix}{} {}", issue.identifier, issue.title)
}

fn format_ready_line(issue: &IssueData) -> String {
    let prefix = issue
        .custom
        .get("project_path")
        .and_then(|value| value.as_str())
        .map(|value| format!("{value} "))
        .unwrap_or_default();
    format!("{prefix}{}", issue.identifier)
}

fn is_issue_blocked(issue: &IssueData) -> bool {
    issue
        .dependencies
        .iter()
        .any(|dependency| dependency.dependency_type == "blocked-by")
}
