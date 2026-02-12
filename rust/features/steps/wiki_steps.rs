use std::fs;
use std::path::PathBuf;

use chrono::{TimeZone, Utc};
use cucumber::{gherkin::Step, given, then, when};

use taskulus::cli::run_from_args_with_output;
use taskulus::file_io::load_project_directory;
use taskulus::models::IssueData;

use crate::step_definitions::initialization_steps::TaskulusWorld;

fn run_cli(world: &mut TaskulusWorld, command: &str) {
    let args = shell_words::split(command).expect("parse command");
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");

    match run_from_args_with_output(args, cwd.as_path()) {
        Ok(output) => {
            world.exit_code = Some(0);
            world.stdout = Some(output.stdout);
            world.stderr = Some(String::new());
        }
        Err(error) => {
            world.exit_code = Some(1);
            world.stdout = Some(String::new());
            world.stderr = Some(error.to_string());
        }
    }
}

fn load_project_dir(world: &TaskulusWorld) -> PathBuf {
    let cwd = world.working_directory.as_ref().expect("cwd");
    load_project_directory(cwd).expect("project dir")
}

fn write_issue_file(project_dir: &PathBuf, issue: &IssueData) {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{}.json", issue.identifier));
    let contents = serde_json::to_string_pretty(issue).expect("serialize issue");
    fs::write(issue_path, contents).expect("write issue");
}

fn build_issue(identifier: &str, title: &str, status: &str) -> IssueData {
    let timestamp = Utc.with_ymd_and_hms(2026, 2, 11, 0, 0, 0).unwrap();
    IssueData {
        identifier: identifier.to_string(),
        title: title.to_string(),
        description: "".to_string(),
        issue_type: "task".to_string(),
        status: status.to_string(),
        priority: 2,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: Vec::new(),
        comments: Vec::new(),
        created_at: timestamp,
        updated_at: timestamp,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    }
}

#[given("3 open tasks and 2 closed tasks exist")]
fn given_open_and_closed_tasks(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let issues = vec![
        build_issue("tsk-open01", "Open 1", "open"),
        build_issue("tsk-open02", "Open 2", "open"),
        build_issue("tsk-open03", "Open 3", "open"),
        build_issue("tsk-closed01", "Closed 1", "closed"),
        build_issue("tsk-closed02", "Closed 2", "closed"),
    ];
    for issue in issues {
        write_issue_file(&project_dir, &issue);
    }
}

#[given(expr = "open tasks {string} and {string} exist")]
fn given_open_tasks(world: &mut TaskulusWorld, first: String, second: String) {
    let project_dir = load_project_dir(world);
    let issues = vec![
        build_issue("tsk-alpha", &first, "open"),
        build_issue("tsk-beta", &second, "open"),
    ];
    for issue in issues {
        write_issue_file(&project_dir, &issue);
    }
}

#[given("open tasks \"Urgent\" and \"Later\" exist with priorities 1 and 3")]
fn given_open_tasks_with_priorities(world: &mut TaskulusWorld) {
    let project_dir = load_project_dir(world);
    let mut urgent = build_issue("tsk-urgent", "Urgent", "open");
    let mut later = build_issue("tsk-later", "Later", "open");
    urgent.priority = 1;
    later.priority = 3;
    for issue in vec![urgent, later] {
        write_issue_file(&project_dir, &issue);
    }
}

#[given(expr = "a wiki page {string} with content:")]
fn given_wiki_page_with_content(world: &mut TaskulusWorld, filename: String, step: &Step) {
    let project_dir = load_project_dir(world);
    let wiki_dir = project_dir.join("wiki");
    fs::create_dir_all(&wiki_dir).expect("create wiki dir");
    let content = step.docstring().expect("content not found");
    fs::write(wiki_dir.join(filename), content).expect("write wiki page");
}

#[given(expr = "a raw wiki page {string} with content:")]
fn given_raw_wiki_page_with_content(world: &mut TaskulusWorld, filename: String, step: &Step) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let content = step.docstring().expect("content not found");
    fs::write(cwd.join(filename), content).expect("write wiki page");
}

#[when(expr = "I run \"tsk wiki render {string}\"")]
fn when_render_page(world: &mut TaskulusWorld, page: String) {
    run_cli(world, &format!("tsk wiki render {page}"));
}

#[when(expr = "I render the wiki page {string} by absolute path")]
fn when_render_absolute(world: &mut TaskulusWorld, filename: String) {
    let project_dir = load_project_dir(world);
    let page_path = project_dir.join("wiki").join(filename);
    run_cli(world, &format!("tsk wiki render {}", page_path.display()));
}

#[then(expr = "\"{string}\" should appear before \"{string}\" in the output")]
fn then_text_before_text(world: &mut TaskulusWorld, first: String, second: String) {
    let stdout = world.stdout.as_ref().expect("stdout");
    let first_index = stdout.find(&first).expect("first value in stdout");
    let second_index = stdout.find(&second).expect("second value in stdout");
    assert!(first_index < second_index);
}
