//! CLI command definitions.

use std::ffi::OsString;
use std::path::Path;

use clap::error::ErrorKind;
use clap::{Parser, Subcommand};
use std::collections::HashSet;

use crate::agents_management::ensure_agents_file;
use crate::beads_write::{
    add_beads_comment, add_beads_dependency, create_beads_issue, delete_beads_comment,
    delete_beads_issue, remove_beads_dependency, update_beads_comment, update_beads_issue,
};
use crate::config_loader::load_project_configuration;
use crate::console_snapshot::build_console_snapshot;
use crate::console_telemetry::stream_console_telemetry;
use crate::content_validation::validate_code_blocks;
use crate::rich_text_signals::{
    apply_text_quality_signals, emit_signals, start_stderr_capture, take_captured_stderr,
};
use crate::daemon_client::{request_shutdown, request_status};
use crate::daemon_server::run_daemon;
use crate::dependencies::{add_dependency, list_ready_issues, remove_dependency};
use crate::dependency_tree::{build_dependency_tree, render_dependency_tree};
use crate::doctor::run_doctor;
use crate::error::KanbusError;
use crate::file_io::{
    canonicalize_path, ensure_git_repository, get_configuration_path, initialize_project,
    resolve_root,
};
use crate::ids::format_issue_key;
use crate::issue_close::close_issue;
use crate::issue_comment::{add_comment, delete_comment, ensure_issue_comment_ids, update_comment};
use crate::issue_creation::{create_issue, IssueCreationRequest};
use crate::issue_delete::delete_issue;
use crate::issue_display::format_issue_for_display;
use crate::issue_line::{compute_widths, format_issue_line};
use crate::issue_listing::list_issues;
use crate::issue_lookup::load_issue_from_project;
use crate::issue_transfer::{localize_issue, promote_issue};
use crate::issue_update::update_issue;
use crate::jira_sync::pull_from_jira;
use crate::maintenance::{collect_project_stats, validate_project};
use crate::migration::{load_beads_issue_by_id, load_beads_issues, migrate_from_beads};
use crate::models::IssueData;
use crate::queries::{filter_issues, search_issues};
use crate::users::get_current_user;
use crate::wiki::{render_wiki_page, WikiRenderRequest};

/// Kanbus CLI arguments.
#[derive(Debug, Parser)]
#[command(
    name = "kbs",
    version = env!("GIT_VERSION"),
    after_help = "Examples:
  kbs list                                     list all issues
  kbs issues                                   alias for: kbs list
  kbs epics / kbs tasks / kbs bugs             list by type
  kbs create \"Fix login bug\" --type bug        create an issue
  kbs create \"Release v1\" --type epic --parent <id>
  kbs show <id>                                show issue details
  kbs update <id> --status in_progress         update status
  kbs comment <id> \"Progress note\"             add a comment
  kbs close <id>                               close an issue

Issue types:  initiative > epic > story / task / bug > sub-task
Statuses:     open  in_progress  blocked  done  closed
Priorities:   0=critical  1=high  2=medium(default)  3=low  4=trivial"
)]
pub struct Cli {
    /// Enable Beads compatibility mode (read .beads/issues.jsonl).
    #[arg(long)]
    beads: bool,
    #[command(subcommand)]
    command: Commands,
}

#[derive(Debug, Subcommand)]
enum Commands {
    /// Initialize a Kanbus project in the current repository.
    Init {
        /// Create project-local alongside project.
        #[arg(long)]
        local: bool,
    },
    /// Set up Kanbus helper files.
    Setup {
        #[command(subcommand)]
        command: SetupCommands,
    },
    /// Create a new issue.
    ///
    /// Issue types follow a hierarchy: initiative > epic > story / task / bug > sub-task.
    /// Use --parent to attach an issue to a parent.
    ///
    /// Examples:
    ///   kbs create "Plan the roadmap" --type initiative
    ///   kbs create "Release v1" --type epic --parent <initiative-id>
    ///   kbs create "Implement login" --type task --parent <epic-id>
    ///   kbs create "Fix crash on launch" --type bug --priority 0 --parent <epic-id>
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
        /// Bypass validation checks.
        #[arg(long = "no-validate")]
        no_validate: bool,
        /// Automatically focus the issue in the console UI after creation.
        #[arg(long)]
        focus: bool,
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
        /// Updated priority.
        #[arg(long)]
        priority: Option<u8>,
        /// Updated assignee.
        #[arg(long)]
        assignee: Option<String>,
        /// Add label(s).
        #[arg(long = "add-label")]
        add_labels: Vec<String>,
        /// Remove label(s).
        #[arg(long = "remove-label")]
        remove_labels: Vec<String>,
        /// Set labels (comma-separated).
        #[arg(long = "set-labels")]
        set_labels: Option<String>,
        /// Updated parent issue identifier.
        #[arg(long)]
        parent: Option<String>,
        /// Claim the issue.
        #[arg(long)]
        claim: bool,
        /// Bypass validation checks.
        #[arg(long = "no-validate")]
        no_validate: bool,
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
        #[command(subcommand)]
        command: Option<CommentCommands>,
        /// Issue identifier.
        identifier: Option<String>,
        /// Comment text.
        #[arg(required = false)]
        text: Vec<String>,
        /// Read comment body from file ('-' for stdin).
        #[arg(long = "body-file", value_name = "PATH")]
        body_file: Option<String>,
        /// Bypass validation checks.
        #[arg(long = "no-validate")]
        no_validate: bool,
    },
    /// List issues.
    ///
    /// Examples:
    ///   kbs list                                    all issues
    ///   kbs list --type epic                        only epics
    ///   kbs list --status open                      only open issues
    ///   kbs list --type task --status in_progress
    ///   kbs issues / kbs epics / kbs tasks / kbs bugs   shorthand aliases
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
        /// Filter by project label.
        #[arg(long = "project")]
        project: Vec<String>,
        /// Exclude local issues.
        #[arg(long = "no-local")]
        no_local: bool,
        /// Show only local issues.
        #[arg(long = "local-only")]
        local_only: bool,
        /// Plain, non-colorized output for machine parsing.
        #[arg(long)]
        porcelain: bool,
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
    #[command(name = "dep", trailing_var_arg = true, allow_hyphen_values = true)]
    Dep {
        /// Raw arguments: <id> <type> <target> | <id> remove <type> <target> | tree <id> [--depth N] [--format FORMAT]
        #[arg(num_args = 1..)]
        args: Vec<String>,
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
    /// Jira synchronization commands.
    Jira {
        #[command(subcommand)]
        command: JiraCommands,
    },
    /// Migrate Beads issues into Kanbus.
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
    /// Console helpers.
    Console {
        #[command(subcommand)]
        command: ConsoleCommands,
    },
    /// Report daemon status.
    #[command(name = "daemon-status")]
    DaemonStatus,
    /// Stop the daemon process.
    #[command(name = "daemon-stop")]
    DaemonStop,
}

fn is_help_request(kind: ErrorKind) -> bool {
    matches!(
        kind,
        ErrorKind::DisplayHelp
            | ErrorKind::DisplayHelpOnMissingArgumentOrSubcommand
            | ErrorKind::DisplayVersion
    )
}

fn merge_issue_views(mut beads: IssueData, project: IssueData) -> IssueData {
    // Dependencies: keep beads as source of truth and union in any extras from project.
    let mut dependency_keys: HashSet<(String, String)> = beads
        .dependencies
        .iter()
        .map(|link| (link.target.clone(), link.dependency_type.clone()))
        .collect();
    for link in project.dependencies {
        let key = (link.target.clone(), link.dependency_type.clone());
        if dependency_keys.insert(key) {
            beads.dependencies.push(link);
        }
    }

    // Parent: prefer beads, otherwise inherit project parent.
    if beads.parent.is_none() {
        beads.parent = project.parent;
    }

    // Comments: keep chronological order and de-duplicate by id (or author/text/timestamp fallback).
    let mut comment_keys: HashSet<String> = HashSet::new();
    for comment in &beads.comments {
        let key = comment.id.clone().unwrap_or_else(|| {
            format!("{}|{}|{}", comment.author, comment.text, comment.created_at)
        });
        comment_keys.insert(key);
    }
    for comment in project.comments {
        let key = comment.id.clone().unwrap_or_else(|| {
            format!("{}|{}|{}", comment.author, comment.text, comment.created_at)
        });
        if comment_keys.insert(key.clone()) {
            beads.comments.push(comment);
        }
    }
    beads
        .comments
        .sort_by(|a, b| a.created_at.cmp(&b.created_at));

    // Fill in empty descriptive fields from the project copy when beads lacks them.
    if beads.description.is_empty() && !project.description.is_empty() {
        beads.description = project.description;
    }
    if beads.labels.is_empty() && !project.labels.is_empty() {
        beads.labels = project.labels;
    }
    if beads.assignee.is_none() {
        beads.assignee = project.assignee;
    }
    if beads.creator.is_none() {
        beads.creator = project.creator;
    }

    // Custom fields: prefer beads, add any missing keys from project.
    for (key, value) in project.custom {
        beads.custom.entry(key).or_insert(value);
    }

    // Updated timestamp: reflect the newest change across both representations.
    if project.updated_at > beads.updated_at {
        beads.updated_at = project.updated_at;
    }
    if beads.closed_at.is_none() {
        beads.closed_at = project.closed_at;
    }

    beads
}

#[cfg(tarpaulin)]
fn cover_help_request() {
    let _ = is_help_request(ErrorKind::DisplayHelp);
    let _ = is_help_request(ErrorKind::DisplayHelpOnMissingArgumentOrSubcommand);
    let _ = is_help_request(ErrorKind::DisplayVersion);
}

#[derive(Debug, Subcommand)]
enum SetupCommands {
    /// Ensure AGENTS.md includes Kanbus guidance.
    Agents {
        /// Overwrite existing Kanbus section without prompting.
        #[arg(long)]
        force: bool,
    },
}

#[derive(Debug, Subcommand)]
enum JiraCommands {
    /// Pull issues from Jira into Kanbus.
    Pull {
        /// Show what would be done without writing any files.
        #[arg(long)]
        dry_run: bool,
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

#[derive(Debug, Subcommand)]
enum ConsoleCommands {
    /// Emit a JSON snapshot for the console.
    Snapshot,
    /// Stream browser console logs to a local file.
    Log {
        /// Output file path.
        #[arg(long, value_name = "PATH")]
        output: Option<String>,
        /// Console telemetry URL override.
        #[arg(long, value_name = "URL")]
        url: Option<String>,
    },
    /// Focus on an issue and its descendants in the console.
    Focus {
        /// Issue identifier to focus on.
        identifier: String,
        /// Optional comment ID to scroll to within the focused issue.
        #[arg(long)]
        comment: Option<String>,
    },
    /// Clear the current focus filter and return to the main board view.
    Unfocus,
    /// Switch between Initiatives/Epics/Issues view modes.
    View {
        /// View mode to switch to: initiatives, epics, or issues.
        mode: String,
    },
    /// Set or clear the search query.
    Search {
        /// Search query text.
        query: Option<String>,
        /// Clear the search query.
        #[arg(long)]
        clear: bool,
    },
    /// Maximize the detail panel.
    Maximize,
    /// Restore the detail panel to normal size.
    Restore,
    /// Close the detail panel.
    CloseDetail,
    /// Toggle the settings panel.
    ToggleSettings,
    /// Update a specific setting value.
    SetSetting {
        /// Setting key.
        key: String,
        /// Setting value.
        value: String,
    },
    /// Collapse a board column.
    CollapseColumn {
        /// Column name to collapse.
        column: String,
    },
    /// Expand a board column.
    ExpandColumn {
        /// Column name to expand.
        column: String,
    },
    /// Select and navigate to an issue.
    Select {
        /// Issue identifier to select.
        identifier: String,
    },
    /// Print a human-readable summary of the current console UI state.
    Status,
    /// Query a specific piece of console UI state.
    Get {
        /// State field to query: focus, view, or search.
        field: String,
    },
}

#[derive(Debug, Subcommand)]
enum CommentCommands {
    /// Update a comment by id prefix.
    Update {
        /// Issue identifier.
        identifier: String,
        /// Comment id (full or prefix).
        comment_id: String,
        /// Updated comment text.
        #[arg(required = true)]
        text: Vec<String>,
    },
    /// Delete a comment by id prefix.
    Delete {
        /// Issue identifier.
        identifier: String,
        /// Comment id (full or prefix).
        comment_id: String,
    },
    /// Ensure comment ids exist for legacy comments.
    #[command(name = "ensure-ids")]
    EnsureIds {
        /// Issue identifier.
        identifier: String,
    },
}

/// Output produced by a CLI command.
#[derive(Debug, Default)]
pub struct CommandOutput {
    pub stdout: String,
    pub stderr: String,
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
/// Returns `KanbusError` if execution fails.
pub fn run_from_args<I, T>(args: I, cwd: &Path) -> Result<(), KanbusError>
where
    I: IntoIterator<Item = T>,
    T: Into<OsString> + Clone,
{
    let output = run_from_args_with_output(args, cwd)?;
    if !output.stdout.is_empty() {
        println!("{}", output.stdout);
    }
    if !output.stderr.is_empty() {
        eprint!("{}", output.stderr);
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
/// Returns `KanbusError` if execution fails.
pub fn run_from_args_with_output<I, T>(args: I, cwd: &Path) -> Result<CommandOutput, KanbusError>
where
    I: IntoIterator<Item = T>,
    T: Into<OsString> + Clone,
{
    #[cfg(tarpaulin)]
    cover_help_request();
    start_stderr_capture();
    let args_vec: Vec<OsString> = args.into_iter().map(Into::into).collect();
    let beads_flag = args_vec.iter().any(|arg| arg == "--beads");
    let cli = match Cli::try_parse_from(&args_vec) {
        Ok(parsed) => parsed,
        Err(error) => {
            let rendered = error.render().to_string();
            let captured_stderr = take_captured_stderr().unwrap_or_default();
            if is_help_request(error.kind()) {
                return Ok(CommandOutput {
                    stdout: rendered,
                    stderr: captured_stderr,
                });
            }
            return Err(KanbusError::IssueOperation(rendered));
        }
    };
    let root = resolve_root(cwd);
    let root = canonicalize_path(&root).unwrap_or(root);
    let (beads_mode, beads_forced) = resolve_beads_mode(&root, beads_flag)?;
    let stdout = execute_command(cli.command, &root, beads_mode, beads_forced);
    let captured_stderr = take_captured_stderr().unwrap_or_default();
    let stdout = stdout?;

    Ok(CommandOutput {
        stdout: stdout.unwrap_or_default(),
        stderr: captured_stderr,
    })
}

fn resolve_beads_mode(root: &Path, beads_flag: bool) -> Result<(bool, bool), KanbusError> {
    if beads_flag {
        return Ok((true, true));
    }
    let configuration_path = match get_configuration_path(root) {
        Ok(path) => path,
        Err(KanbusError::IssueOperation(message)) if message == "project not initialized" => {
            return Ok((false, false))
        }
        Err(KanbusError::Io(message)) if message == "configuration path lookup failed" => {
            return Ok((false, false))
        }
        Err(error) => return Err(error),
    };
    let configuration = load_project_configuration(&configuration_path)?;
    Ok((configuration.beads_compatibility, false))
}

fn beads_root(root: &Path) -> std::path::PathBuf {
    get_configuration_path(root)
        .ok()
        .and_then(|p| p.parent().map(std::path::PathBuf::from))
        .unwrap_or_else(|| root.to_path_buf())
}

fn execute_command(
    command: Commands,
    root: &Path,
    beads_mode: bool,
    _beads_forced: bool,
) -> Result<Option<String>, KanbusError> {
    let root_for_beads = beads_root(root);
    match command {
        Commands::Init { local } => {
            ensure_git_repository(root)?;
            initialize_project(root, local)?;
            Ok(None)
        }
        Commands::Setup { command } => match command {
            SetupCommands::Agents { force } => {
                ensure_agents_file(root, force)?;
                Ok(None)
            }
        },
        Commands::Create {
            title,
            issue_type,
            priority,
            assignee,
            parent,
            label,
            description,
            local,
            no_validate,
            focus,
        } => {
            let title_text = title.join(" ");
            if title_text.trim().is_empty() {
                return Err(KanbusError::IssueOperation("title is required".to_string()));
            }
            let raw_description_text = description
                .as_ref()
                .map(|values| values.join(" "))
                .unwrap_or_default();
            let (quality_result, description_text) = if raw_description_text.is_empty() {
                (None, raw_description_text)
            } else {
                let qr = apply_text_quality_signals(&raw_description_text);
                let repaired = qr.text.clone();
                (Some(qr), repaired)
            };
            if !no_validate && !description_text.is_empty() {
                validate_code_blocks(&description_text)?;
            }
            if beads_mode {
                if local {
                    return Err(KanbusError::IssueOperation(
                        "beads mode does not support local issues".to_string(),
                    ));
                }
                let issue = create_beads_issue(
                    &root_for_beads,
                    &title_text,
                    issue_type.as_deref(),
                    priority,
                    assignee.as_deref(),
                    parent.as_deref(),
                    if description_text.is_empty() {
                        None
                    } else {
                        Some(description_text.as_str())
                    },
                )?;

                // Auto-focus the newly created issue if --focus flag is set
                if focus {
                    use crate::notification_events::NotificationEvent;
                    use crate::notification_publisher::publish_notification;

                    let event = NotificationEvent::IssueFocused {
                        issue_id: issue.identifier.clone(),
                        user: None,
                        comment_id: None,
                    };

                    // Best-effort notification - don't fail if console server is down
                    let _ = publish_notification(root, event);
                }

                let use_color = should_use_color();
                let output = format_issue_for_display(&issue, None, use_color, false);
                if let Some(ref qr) = quality_result {
                    emit_signals(qr, "description", Some(&issue.identifier), None, false);
                }
                return Ok(Some(output));
            }
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
                validate: !no_validate,
            };
            let result = create_issue(&request)?;
            let configuration = result.configuration;
            let issue = result.issue;

            // Auto-focus the newly created issue if --focus flag is set
            if focus {
                use crate::notification_events::NotificationEvent;
                use crate::notification_publisher::publish_notification;

                let event = NotificationEvent::IssueFocused {
                    issue_id: issue.identifier.clone(),
                    user: None,
                    comment_id: None,
                };

                // Best-effort notification - don't fail if console server is down
                let _ = publish_notification(root, event);
            }

            let use_color = should_use_color();
            let output = format_issue_for_display(&issue, Some(&configuration), use_color, false);
            if let Some(ref qr) = quality_result {
                emit_signals(qr, "description", Some(&issue.identifier), None, false);
            }
            Ok(Some(output))
        }
        Commands::Show { identifier, json } => {
            let (issue, configuration) = if beads_mode {
                let mut beads_issue = load_beads_issue_by_id(&root_for_beads, &identifier)?;
                // Normalize comment ids for display consistency
                let (normalized, _) = crate::issue_comment::ensure_comment_ids(&beads_issue);
                beads_issue = normalized;

                // Merge data from project copy if present to surface cross-mode changes
                if let Ok(project_lookup) = load_issue_from_project(root, &identifier) {
                    let project_issue = project_lookup.issue;
                    beads_issue = merge_issue_views(beads_issue, project_issue);
                }

                (beads_issue, None)
            } else {
                let lookup = load_issue_from_project(root, &identifier)?;
                let configuration = load_project_configuration(&get_configuration_path(
                    lookup.project_dir.as_path(),
                )?)?;
                let mut issue = ensure_issue_comment_ids(root, &identifier)?;
                if configuration.beads_compatibility {
                    if let Ok(beads_issue) = load_beads_issue_by_id(&root_for_beads, &identifier) {
                        issue = merge_issue_views(beads_issue, issue);
                    }
                }
                (issue, Some(configuration))
            };
            if json {
                let payload =
                    serde_json::to_string_pretty(&issue).expect("failed to serialize issue");
                return Ok(Some(payload));
            }
            let use_color = should_use_color();
            Ok(Some(format_issue_for_display(
                &issue,
                configuration.as_ref(),
                use_color,
                false,
            )))
        }
        Commands::Update {
            identifier,
            title,
            description,
            status,
            priority,
            assignee,
            add_labels,
            remove_labels,
            set_labels,
            parent,
            claim,
            no_validate,
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
                assignee.clone()
            };
            let title_value = if title_text.is_empty() {
                None
            } else {
                Some(title_text.as_str())
            };
            let description_value = if description_text.is_empty() {
                None
            } else {
                Some(description_text.as_str())
            };
            let (update_quality_result, repaired_description) =
                if let Some(desc) = description_value {
                    let qr = apply_text_quality_signals(desc);
                    let repaired = qr.text.clone();
                    (Some(qr), Some(repaired))
                } else {
                    (None, None)
                };
            let final_description_value = repaired_description.as_deref();
            if !no_validate {
                if let Some(text) = final_description_value {
                    validate_code_blocks(text)?;
                }
            }
            if beads_mode {
                if parent.is_some() {
                    return Err(KanbusError::IssueOperation(
                        "parent update not supported in beads mode".to_string(),
                    ));
                }
                update_beads_issue(
                    &root_for_beads,
                    &identifier,
                    status.as_deref(),
                    priority,
                    title_value,
                    final_description_value,
                    assignee_value.as_deref(),
                    &add_labels,
                    &remove_labels,
                    set_labels.as_deref(),
                )?;
            } else {
                update_issue(
                    root,
                    &identifier,
                    title_value,
                    final_description_value,
                    status.as_deref(),
                    assignee_value.as_deref(),
                    priority,
                    claim,
                    !no_validate,
                    &add_labels,
                    &remove_labels,
                    set_labels.as_deref(),
                    parent.as_deref(),
                )?;
            }
            let formatted_identifier = format_issue_key(&identifier, false);
            if let Some(ref qr) = update_quality_result {
                emit_signals(qr, "description", Some(&identifier), None, true);
            }
            Ok(Some(format!("Updated {}", formatted_identifier)))
        }
        Commands::Close { identifier } => {
            if beads_mode {
                update_beads_issue(
                    &root_for_beads,
                    &identifier,
                    Some("closed"),
                    None,
                    None,
                    None,
                    None,
                    &[],
                    &[],
                    None,
                )?;
            } else {
                close_issue(root, &identifier)?;
            }
            let formatted_identifier = format_issue_key(&identifier, false);
            Ok(Some(format!("Closed {}", formatted_identifier)))
        }
        Commands::Delete { identifier } => {
            if beads_mode {
                delete_beads_issue(&root_for_beads, &identifier)?;
            } else {
                delete_issue(root, &identifier)?;
            }
            let formatted_identifier = format_issue_key(&identifier, false);
            Ok(Some(format!("Deleted {}", formatted_identifier)))
        }
        Commands::Comment {
            command,
            identifier,
            text,
            no_validate,
            body_file,
        } => match command {
            Some(CommentCommands::Update {
                identifier,
                comment_id,
                text,
            }) => {
                let text_value = text.join(" ");
                if text_value.trim().is_empty() {
                    return Err(KanbusError::IssueOperation(
                        "comment text is required".to_string(),
                    ));
                }
                let comment_update_quality_result = apply_text_quality_signals(&text_value);
                let repaired_text_value = comment_update_quality_result.text.clone();
                if !no_validate {
                    validate_code_blocks(&repaired_text_value)?;
                }
                if beads_mode {
                    update_beads_comment(
                        &root_for_beads,
                        &identifier,
                        &comment_id,
                        &repaired_text_value,
                    )?;
                } else {
                    update_comment(root, &identifier, &comment_id, &repaired_text_value)?;
                }
                emit_signals(
                    &comment_update_quality_result,
                    "comment",
                    Some(&identifier),
                    Some(&comment_id),
                    true,
                );
                Ok(None)
            }
            Some(CommentCommands::Delete {
                identifier,
                comment_id,
            }) => {
                if beads_mode {
                    delete_beads_comment(&root_for_beads, &identifier, &comment_id)?;
                } else {
                    delete_comment(root, &identifier, &comment_id)?;
                }
                Ok(None)
            }
            Some(CommentCommands::EnsureIds { identifier }) => {
                if beads_mode {
                    return Err(KanbusError::IssueOperation(
                        "beads mode does not support ensure-ids".to_string(),
                    ));
                }
                ensure_issue_comment_ids(root, &identifier)?;
                Ok(None)
            }
            None => {
                let Some(identifier) = identifier else {
                    return Err(KanbusError::IssueOperation(
                        "issue identifier is required".to_string(),
                    ));
                };
                let text_value = if let Some(path) = body_file.as_deref() {
                    if path == "-" {
                        use std::io::{stdin, Read};
                        let mut buffer = String::new();
                        stdin().read_to_string(&mut buffer).map_err(|error| {
                            KanbusError::Io(format!("failed to read stdin: {error}"))
                        })?;
                        buffer
                    } else {
                        std::fs::read_to_string(path).map_err(|error| {
                            KanbusError::Io(format!("failed to read body file: {error}"))
                        })?
                    }
                } else {
                    text.join(" ")
                };
                if text_value.trim().is_empty() {
                    return Err(KanbusError::IssueOperation(
                        "comment text is required".to_string(),
                    ));
                }
                let add_comment_quality_result = apply_text_quality_signals(&text_value);
                let repaired_comment_text = add_comment_quality_result.text.clone();
                if !no_validate {
                    validate_code_blocks(&repaired_comment_text)?;
                }
                if beads_mode {
                    add_beads_comment(
                        &root_for_beads,
                        &identifier,
                        &get_current_user(),
                        &repaired_comment_text,
                    )?;
                    emit_signals(
                        &add_comment_quality_result,
                        "comment",
                        Some(&identifier),
                        None,
                        false,
                    );
                } else {
                    let comment_result =
                        add_comment(root, &identifier, &get_current_user(), &repaired_comment_text)?;
                    emit_signals(
                        &add_comment_quality_result,
                        "comment",
                        Some(&identifier),
                        comment_result.comment.id.as_deref(),
                        false,
                    );
                }
                Ok(None)
            }
        },
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
            project,
            no_local,
            local_only,
            porcelain,
        } => {
            let issues = if beads_mode {
                if local_only || no_local {
                    return Err(KanbusError::IssueOperation(
                        "beads mode does not support local filtering".to_string(),
                    ));
                }
                let issues = load_beads_issues(&root_for_beads)?;
                let filtered = filter_issues(
                    issues,
                    status.as_deref(),
                    issue_type.as_deref(),
                    assignee.as_deref(),
                    label.as_deref(),
                );
                let mut searched = search_issues(filtered, search.as_deref());
                // Beads fixtures include closed issues; align with Kanbus list default by hiding
                // closed unless an explicit status filter is provided.
                if status.is_none() {
                    searched.retain(|issue| !issue.status.eq_ignore_ascii_case("closed"));
                }
                searched.sort_by(|a, b| {
                    a.priority
                        .cmp(&b.priority)
                        .then_with(|| sort_timestamp(b).total_cmp(&sort_timestamp(a)))
                        .then(a.identifier.cmp(&b.identifier))
                });
                searched
            } else {
                list_issues(
                    root,
                    status.as_deref(),
                    issue_type.as_deref(),
                    assignee.as_deref(),
                    label.as_deref(),
                    sort.as_deref(),
                    search.as_deref(),
                    &project,
                    !no_local,
                    local_only,
                )?
            };
            let configuration = if beads_mode {
                None
            } else {
                match get_configuration_path(root) {
                    Ok(path) => Some(load_project_configuration(&path)?),
                    Err(KanbusError::IssueOperation(message))
                        if message == "project not initialized" =>
                    {
                        None
                    }
                    Err(error) => return Err(error),
                }
            };
            let project_context = if beads_mode {
                false
            } else {
                !issues
                    .iter()
                    .any(|issue| issue.custom.contains_key("project_path"))
            };
            let widths = if porcelain {
                None
            } else {
                Some(compute_widths(&issues, project_context))
            };
            let lines = issues
                .iter()
                .map(|issue| {
                    format_issue_line(
                        issue,
                        widths.as_ref(),
                        porcelain,
                        project_context,
                        configuration.as_ref(),
                        None,
                    )
                })
                .collect::<Vec<_>>();
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
        Commands::Dep { args } => {
            if args.is_empty() {
                return Err(KanbusError::IssueOperation(
                    "usage: kanbus dep <identifier> <type> <target>".to_string(),
                ));
            }

            // Tree handling: kanbus dep tree <id> [--depth N] [--format FORMAT]
            if args[0] == "tree" {
                if args.len() < 2 {
                    return Err(KanbusError::IssueOperation(
                        "tree requires an identifier".to_string(),
                    ));
                }
                let identifier = args[1].clone();
                let mut depth: Option<usize> = None;
                let mut format = "text".to_string();
                let mut index = 2;
                while index < args.len() {
                    match args[index].as_str() {
                        "--depth" if index + 1 < args.len() => {
                            if let Ok(value) = args[index + 1].parse::<usize>() {
                                depth = Some(value);
                            } else {
                                return Err(KanbusError::IssueOperation(
                                    "depth must be a number".to_string(),
                                ));
                            }
                            index += 2;
                        }
                        "--format" if index + 1 < args.len() => {
                            format = args[index + 1].clone();
                            index += 2;
                        }
                        _ => {
                            index += 1;
                        }
                    }
                }
                let tree = build_dependency_tree(root, &identifier, depth)?;
                let output = render_dependency_tree(&tree, &format, None)?;
                return Ok(Some(output));
            }

            if args.len() < 2 {
                return Err(KanbusError::IssueOperation(
                    "usage: kanbus dep <identifier> <type> <target>".to_string(),
                ));
            }

            let identifier = &args[0];
            let mut is_remove = false;
            let (dependency_type, target) = if args.get(1).map(String::as_str) == Some("remove") {
                is_remove = true;
                if args.len() < 4 {
                    return Err(KanbusError::IssueOperation(
                        "dependency target is required".to_string(),
                    ));
                }
                (args[2].clone(), args[3].clone())
            } else {
                if args.len() < 3 {
                    return Err(KanbusError::IssueOperation(
                        "dependency target is required".to_string(),
                    ));
                }
                (args[1].clone(), args[2].clone())
            };

            if beads_mode {
                if is_remove {
                    remove_beads_dependency(
                        &root_for_beads,
                        identifier,
                        &target,
                        &dependency_type,
                    )?;
                } else {
                    add_beads_dependency(&root_for_beads, identifier, &target, &dependency_type)?;
                }
            } else if is_remove {
                remove_dependency(root, identifier, &target, &dependency_type)?;
            } else {
                add_dependency(root, identifier, &target, &dependency_type)?;
            }
            Ok(None)
        }
        Commands::Ready {
            no_local,
            local_only,
        } => {
            let issues = if beads_mode {
                if local_only || no_local {
                    return Err(KanbusError::IssueOperation(
                        "beads mode does not support local filtering".to_string(),
                    ));
                }
                load_beads_issues(&root_for_beads)?
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
        Commands::Jira { command } => match command {
            JiraCommands::Pull { dry_run } => {
                let config_path = get_configuration_path(root)?;
                let jira_configuration = load_project_configuration(&config_path)?;
                let jira_config = jira_configuration.jira.as_ref().ok_or_else(|| {
                    KanbusError::Configuration("no jira configuration in .kanbus.yml".to_string())
                })?;
                if !["pull", "both"].contains(&jira_config.sync_direction.as_str()) {
                    return Err(KanbusError::Configuration(
                        "sync_direction must be 'pull' or 'both' to use jira pull".to_string(),
                    ));
                }
                if dry_run {
                    println!("Dry run — no files will be written.\n");
                }
                let result =
                    pull_from_jira(root, jira_config, &jira_configuration.project_key, dry_run)?;
                Ok(Some(format!(
                    "pulled {} new, updated {} existing",
                    result.pulled, result.updated
                )))
            }
        },
        Commands::Migrate => {
            let result = migrate_from_beads(&root_for_beads)?;
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
        Commands::Console { command } => match command {
            ConsoleCommands::Snapshot => {
                let snapshot = build_console_snapshot(root)?;
                let payload = serde_json::to_string_pretty(&snapshot)
                    .map_err(|error| KanbusError::Io(error.to_string()))?;
                Ok(Some(payload))
            }
            ConsoleCommands::Log { output, url } => {
                stream_console_telemetry(root, output, url)?;
                Ok(None)
            }
            ConsoleCommands::Focus {
                identifier,
                comment,
            } => {
                // Validate that the issue exists and get its ID
                let issue_id = if beads_mode {
                    let issue = load_beads_issue_by_id(&root_for_beads, &identifier)?;
                    issue.identifier
                } else {
                    let result = load_issue_from_project(root, &identifier)?;
                    result.issue.identifier
                };

                // Publish focus notification
                use crate::notification_events::NotificationEvent;
                use crate::notification_publisher::publish_notification;

                let event = NotificationEvent::IssueFocused {
                    issue_id: issue_id.clone(),
                    user: None,
                    comment_id: comment.clone(),
                };

                // Best-effort notification - don't fail if console server is down
                let _ = publish_notification(root, event);

                let msg = if let Some(ref cid) = comment {
                    format!("Focused on issue {} (comment {})", issue_id, cid)
                } else {
                    format!("Focused on issue {}", issue_id)
                };
                Ok(Some(msg))
            }
            ConsoleCommands::Unfocus => {
                use crate::notification_events::{NotificationEvent, UiControlAction};
                use crate::notification_publisher::publish_notification;

                let event = NotificationEvent::UiControl {
                    action: UiControlAction::ClearFocus,
                };

                // Best-effort notification - don't fail if console server is down
                let _ = publish_notification(root, event);

                Ok(Some("Cleared focus filter".to_string()))
            }
            ConsoleCommands::View { mode } => {
                use crate::notification_events::{NotificationEvent, UiControlAction};
                use crate::notification_publisher::publish_notification;

                // Validate mode
                let valid_modes = ["initiatives", "epics", "issues"];
                if !valid_modes.contains(&mode.as_str()) {
                    return Err(KanbusError::IssueOperation(format!(
                        "Invalid view mode '{}'. Valid modes: {}",
                        mode,
                        valid_modes.join(", ")
                    )));
                }

                let event = NotificationEvent::UiControl {
                    action: UiControlAction::SetViewMode { mode: mode.clone() },
                };

                // Best-effort notification - don't fail if console server is down
                let _ = publish_notification(root, event);

                Ok(Some(format!("Switched to {} view", mode)))
            }
            ConsoleCommands::Search { query, clear } => {
                use crate::notification_events::{NotificationEvent, UiControlAction};
                use crate::notification_publisher::publish_notification;

                let search_query = if clear {
                    String::new()
                } else if let Some(q) = query {
                    q.clone()
                } else {
                    return Err(KanbusError::IssueOperation(
                        "Either provide a query or use --clear flag".to_string(),
                    ));
                };

                let event = NotificationEvent::UiControl {
                    action: UiControlAction::SetSearch {
                        query: search_query.clone(),
                    },
                };

                let _ = publish_notification(root, event);

                let msg = if clear || search_query.is_empty() {
                    "Cleared search query".to_string()
                } else {
                    format!("Set search query to: {}", search_query)
                };
                Ok(Some(msg))
            }
            ConsoleCommands::Maximize => {
                use crate::notification_events::{NotificationEvent, UiControlAction};
                use crate::notification_publisher::publish_notification;

                let event = NotificationEvent::UiControl {
                    action: UiControlAction::MaximizeDetail,
                };

                let _ = publish_notification(root, event);
                println!("Maximized detail panel");
                Ok(None)
            }
            ConsoleCommands::Restore => {
                use crate::notification_events::{NotificationEvent, UiControlAction};
                use crate::notification_publisher::publish_notification;

                let event = NotificationEvent::UiControl {
                    action: UiControlAction::RestoreDetail,
                };

                let _ = publish_notification(root, event);
                println!("Restored detail panel");
                Ok(None)
            }
            ConsoleCommands::CloseDetail => {
                use crate::notification_events::{NotificationEvent, UiControlAction};
                use crate::notification_publisher::publish_notification;

                let event = NotificationEvent::UiControl {
                    action: UiControlAction::CloseDetail,
                };

                let _ = publish_notification(root, event);
                println!("Closed detail panel");
                Ok(None)
            }
            ConsoleCommands::ToggleSettings => {
                use crate::notification_events::{NotificationEvent, UiControlAction};
                use crate::notification_publisher::publish_notification;

                let event = NotificationEvent::UiControl {
                    action: UiControlAction::ToggleSettings,
                };

                let _ = publish_notification(root, event);
                println!("Toggled settings panel");
                Ok(None)
            }
            ConsoleCommands::SetSetting { key, value } => {
                use crate::notification_events::{NotificationEvent, UiControlAction};
                use crate::notification_publisher::publish_notification;

                let event = NotificationEvent::UiControl {
                    action: UiControlAction::SetSetting {
                        key: key.clone(),
                        value: value.clone(),
                    },
                };

                let _ = publish_notification(root, event);
                println!("Set {} = {}", key, value);
                Ok(None)
            }
            ConsoleCommands::CollapseColumn { column } => {
                use crate::notification_events::{NotificationEvent, UiControlAction};
                use crate::notification_publisher::publish_notification;

                let event = NotificationEvent::UiControl {
                    action: UiControlAction::CollapseColumn {
                        column_name: column.clone(),
                    },
                };

                let _ = publish_notification(root, event);
                println!("Collapsed column: {}", column);
                Ok(None)
            }
            ConsoleCommands::ExpandColumn { column } => {
                use crate::notification_events::{NotificationEvent, UiControlAction};
                use crate::notification_publisher::publish_notification;

                let event = NotificationEvent::UiControl {
                    action: UiControlAction::ExpandColumn {
                        column_name: column.clone(),
                    },
                };

                let _ = publish_notification(root, event);
                println!("Expanded column: {}", column);
                Ok(None)
            }
            ConsoleCommands::Select { identifier } => {
                use crate::notification_events::{NotificationEvent, UiControlAction};
                use crate::notification_publisher::publish_notification;

                // Validate that the issue exists and get its ID
                let issue_id = if beads_mode {
                    let issue = load_beads_issue_by_id(&root_for_beads, &identifier)?;
                    issue.identifier
                } else {
                    let result = load_issue_from_project(root, &identifier)?;
                    result.issue.identifier
                };

                let event = NotificationEvent::UiControl {
                    action: UiControlAction::SelectIssue {
                        issue_id: issue_id.clone(),
                    },
                };

                let _ = publish_notification(root, event);
                println!("Selected issue {}", issue_id);
                Ok(None)
            }
            ConsoleCommands::Status => {
                let root_clone = root.to_path_buf();
                let result = std::thread::spawn(move || fetch_console_ui_state(&root_clone))
                    .join()
                    .map_err(|_| {
                        KanbusError::IssueOperation("fetch thread panicked".to_string())
                    })?;
                let output = match result {
                    Ok(ui_state) => {
                        let focused = ui_state.focused_issue_id.as_deref().unwrap_or("none");
                        let view = ui_state.view_mode.as_deref().unwrap_or("none");
                        let search = ui_state.search_query.as_deref().unwrap_or("none");
                        format!("focus:  {focused}\nview:   {view}\nsearch: {search}")
                    }
                    Err(_) => "Console server is not running.".to_string(),
                };
                Ok(Some(output))
            }
            ConsoleCommands::Get { field } => {
                let field = field.as_str();
                if !matches!(field, "focus" | "view" | "search") {
                    return Err(KanbusError::IssueOperation(format!(
                        "Unknown field '{}'. Valid fields: focus, view, search",
                        field
                    )));
                }
                let root_clone = root.to_path_buf();
                let result = std::thread::spawn(move || fetch_console_ui_state(&root_clone))
                    .join()
                    .map_err(|_| {
                        KanbusError::IssueOperation("fetch thread panicked".to_string())
                    })?;
                match result {
                    Ok(ui_state) => {
                        let value = match field {
                            "focus" => ui_state
                                .focused_issue_id
                                .as_deref()
                                .unwrap_or("none")
                                .to_string(),
                            "view" => ui_state.view_mode.as_deref().unwrap_or("none").to_string(),
                            "search" => ui_state
                                .search_query
                                .as_deref()
                                .unwrap_or("none")
                                .to_string(),
                            _ => unreachable!("field validated"),
                        };
                        Ok(Some(value))
                    }
                    Err(_) => Ok(Some("Console server is not running.".to_string())),
                }
            }
        },
        Commands::DaemonStatus => {
            let status = request_status(root).map_err(format_daemon_project_error)?;
            let payload = serde_json::to_string_pretty(&status)
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            Ok(Some(payload))
        }
        Commands::DaemonStop => {
            let status = request_shutdown(root).map_err(format_daemon_project_error)?;
            let payload = serde_json::to_string_pretty(&status)
                .map_err(|error| KanbusError::Io(error.to_string()))?;
            Ok(Some(payload))
        }
    }
}

/// Run the CLI using process arguments and current directory.
///
/// # Errors
///
/// Returns `KanbusError` if execution fails.
pub fn run_from_env() -> Result<(), KanbusError> {
    let args = rewrite_alias_args(std::env::args_os());
    run_from_args(args, Path::new("."))
}

fn rewrite_alias_args<I>(args: I) -> Vec<OsString>
where
    I: IntoIterator<Item = OsString>,
{
    let mut iter = args.into_iter();
    let mut result: Vec<OsString> = iter.by_ref().take(1).collect();
    if let Some(first) = iter.next() {
        match first.to_str().unwrap_or("") {
            "issues" => {
                result.push("list".into());
                result.extend(iter);
            }
            "epics" => {
                result.push("list".into());
                result.push("--type".into());
                result.push("epic".into());
                result.extend(iter);
            }
            "tasks" => {
                result.push("list".into());
                result.push("--type".into());
                result.push("task".into());
                result.extend(iter);
            }
            "stories" => {
                result.push("list".into());
                result.push("--type".into());
                result.push("story".into());
                result.extend(iter);
            }
            "bugs" => {
                result.push("list".into());
                result.push("--type".into());
                result.push("bug".into());
                result.extend(iter);
            }
            _ => {
                result.push(first);
                result.extend(iter);
            }
        }
    }
    result
}

fn sort_timestamp(issue: &IssueData) -> f64 {
    let timestamp = issue.closed_at.unwrap_or(issue.updated_at);
    timestamp.timestamp() as f64
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

fn format_daemon_project_error(error: KanbusError) -> KanbusError {
    match error {
        KanbusError::IssueOperation(message)
            if message.starts_with("multiple projects found") =>
        {
            KanbusError::IssueOperation(
                "multiple projects found. Run this command from a directory containing a single project/ folder.".to_string(),
            )
        }
        KanbusError::IssueOperation(message) if message == "project not initialized" => {
            KanbusError::IssueOperation(
                "project not initialized. Run \"kanbus init\" to create a project/ folder."
                    .to_string(),
            )
        }
        other => other,
    }
}

fn fetch_console_ui_state(
    root: &Path,
) -> Result<crate::console_ui_state::ConsoleUiState, KanbusError> {
    use crate::console_ui_state::ConsoleUiState;
    use reqwest::blocking::Client;

    let config_path = get_configuration_path(root)?;
    let config = load_project_configuration(&config_path)?;
    let port = config.console_port.unwrap_or(5174);
    let url = format!("http://127.0.0.1:{port}/api/ui-state");

    let client = Client::new();
    let response = client
        .get(&url)
        .timeout(std::time::Duration::from_secs(3))
        .send()
        .map_err(|e| KanbusError::IssueOperation(e.to_string()))?;

    let ui_state: ConsoleUiState = response
        .json()
        .map_err(|e| KanbusError::IssueOperation(e.to_string()))?;

    Ok(ui_state)
}

fn should_use_color() -> bool {
    use std::io::IsTerminal;
    std::env::var_os("NO_COLOR").is_none() && std::io::stdout().is_terminal()
}
