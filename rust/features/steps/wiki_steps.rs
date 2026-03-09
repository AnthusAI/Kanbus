use std::fs;
use std::path::PathBuf;
use std::process::Command;

use chrono::{TimeZone, Utc};
use cucumber::{gherkin::Step, given, then, when};
use serde_yaml::{Mapping, Value};
use tempfile::TempDir;

use kanbus::cli::run_from_args_with_output;
use kanbus::file_io::load_project_directory;
use kanbus::models::{IssueComment, IssueData};

use crate::step_definitions::initialization_steps::KanbusWorld;

fn run_cli(world: &mut KanbusWorld, command: &str) {
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

fn load_project_dir(world: &KanbusWorld) -> PathBuf {
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

#[given("3 open tasks exist")]
fn given_three_open_tasks(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issues = vec![
        build_issue("kanbus-open01", "Open 1", "open"),
        build_issue("kanbus-open02", "Open 2", "open"),
        build_issue("kanbus-open03", "Open 3", "open"),
    ];
    for issue in issues {
        write_issue_file(&project_dir, &issue);
    }
}

#[given("3 open tasks and 2 closed tasks exist")]
fn given_open_and_closed_tasks(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let issues = vec![
        build_issue("kanbus-open01", "Open 1", "open"),
        build_issue("kanbus-open02", "Open 2", "open"),
        build_issue("kanbus-open03", "Open 3", "open"),
        build_issue("kanbus-closed01", "Closed 1", "closed"),
        build_issue("kanbus-closed02", "Closed 2", "closed"),
    ];
    for issue in issues {
        write_issue_file(&project_dir, &issue);
    }
}

#[given(expr = "open tasks {string} and {string} exist")]
fn given_open_tasks(world: &mut KanbusWorld, first: String, second: String) {
    let project_dir = load_project_dir(world);
    let issues = vec![
        build_issue("kanbus-alpha", &first, "open"),
        build_issue("kanbus-beta", &second, "open"),
    ];
    for issue in issues {
        write_issue_file(&project_dir, &issue);
    }
}

#[given("open tasks \"Urgent\" and \"Later\" exist with priorities 1 and 3")]
fn given_open_tasks_with_priorities(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let mut urgent = build_issue("kanbus-urgent", "Urgent", "open");
    let mut later = build_issue("kanbus-later", "Later", "open");
    urgent.priority = 1;
    later.priority = 3;
    for issue in vec![urgent, later] {
        write_issue_file(&project_dir, &issue);
    }
}

#[given(expr = "a wiki page {string} with content {string}")]
fn given_wiki_page_with_content_string(world: &mut KanbusWorld, filename: String, content: String) {
    let project_dir = load_project_dir(world);
    let wiki_subdir = world
        .wiki_directory
        .as_ref()
        .map(|s| s.as_str())
        .unwrap_or("wiki");
    let wiki_dir = if wiki_subdir.starts_with("../") {
        let cwd = world.working_directory.as_ref().expect("working dir");
        cwd.join(
            wiki_subdir
                .trim_start_matches("../")
                .trim_start_matches("..\\"),
        )
    } else {
        project_dir.join(wiki_subdir)
    };
    fs::create_dir_all(&wiki_dir).expect("create wiki dir");
    let target = wiki_dir.join(&filename);
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).expect("create wiki parent dir");
    }
    fs::write(target, content).expect("write wiki page");
}

#[given(expr = "a wiki page {string} with content")]
#[given(expr = "a wiki page {string} with content:")]
fn given_wiki_page_with_content(world: &mut KanbusWorld, filename: String, step: &Step) {
    let project_dir = load_project_dir(world);
    let wiki_subdir = world
        .wiki_directory
        .as_ref()
        .map(|s| s.as_str())
        .unwrap_or("wiki");
    let wiki_dir = if wiki_subdir.starts_with("../") {
        let cwd = world.working_directory.as_ref().expect("working dir");
        cwd.join(
            wiki_subdir
                .trim_start_matches("../")
                .trim_start_matches("..\\"),
        )
    } else {
        project_dir.join(wiki_subdir)
    };
    fs::create_dir_all(&wiki_dir).expect("create wiki dir");
    let content = step.docstring().map(|s| s.as_str()).unwrap_or("");
    let target = wiki_dir.join(&filename);
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).expect("create wiki parent dir");
    }
    fs::write(target, content).expect("write wiki page");
}

#[given(expr = "a raw wiki page {string} with content")]
#[given(expr = "a raw wiki page {string} with content:")]
fn given_raw_wiki_page_with_content(world: &mut KanbusWorld, filename: String, step: &Step) {
    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");
    let content = step.docstring().expect("content not found");
    fs::write(cwd.join(filename), content).expect("write wiki page");
}

#[when(expr = "I render the wiki page {string} by absolute path")]
fn when_render_absolute(world: &mut KanbusWorld, filename: String) {
    let project_dir = load_project_dir(world);
    let page_path = project_dir.join("wiki").join(filename);
    run_cli(
        world,
        &format!("kanbus wiki render {}", page_path.display()),
    );
}

#[then(expr = "{string} should appear before {string} in the output")]
fn then_text_before_text(world: &mut KanbusWorld, first: String, second: String) {
    let stdout = world.stdout.as_ref().expect("stdout");
    let first_index = stdout.find(&first).expect("first value in stdout");
    let second_index = stdout.find(&second).expect("second value in stdout");
    assert!(first_index < second_index);
}

fn read_issue_file(project_dir: &PathBuf, identifier: &str) -> IssueData {
    let issue_path = project_dir
        .join("issues")
        .join(format!("{identifier}.json"));
    let contents = fs::read_to_string(&issue_path).expect("read issue");
    serde_json::from_str(&contents).expect("parse issue")
}

#[given(expr = "issue {string} has description containing:")]
fn given_issue_has_description_containing(
    world: &mut KanbusWorld,
    identifier: String,
    step: &Step,
) {
    let project_dir = load_project_dir(world);
    let content = step.docstring().map(|s| s.as_str()).unwrap_or("");
    let mut issue = if project_dir
        .join("issues")
        .join(format!("{identifier}.json"))
        .exists()
    {
        read_issue_file(&project_dir, &identifier)
    } else {
        build_issue(&identifier, "Title", "open")
    };
    issue.description = content.to_string();
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "a comment on issue {string} contains {string}")]
fn given_comment_contains(world: &mut KanbusWorld, identifier: String, text: String) {
    let project_dir = load_project_dir(world);
    let mut issue = read_issue_file(&project_dir, &identifier);
    let author = world.current_user.as_deref().unwrap_or("dev@example.com");
    issue.comments.push(IssueComment {
        id: None,
        author: author.to_string(),
        text,
        created_at: Utc::now(),
    });
    write_issue_file(&project_dir, &issue);
}

#[given(expr = "a comment on issue {string} contains:")]
fn given_comment_contains_multiline(world: &mut KanbusWorld, identifier: String, step: &Step) {
    let text = step
        .docstring()
        .map(|s| s.as_str())
        .unwrap_or("")
        .to_string();
    given_comment_contains(world, identifier, text);
}

#[then(expr = "the rendered description should contain a link to wiki path {string}")]
fn then_rendered_description_has_wiki_link(world: &mut KanbusWorld, path: String) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(
        stdout.contains(&path),
        "expected wiki path {path:?} in output"
    );
}

#[then(expr = "the rendered comments should contain a link to wiki path {string}")]
fn then_rendered_comments_has_wiki_link(world: &mut KanbusWorld, path: String) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(
        stdout.contains(&path),
        "expected wiki path {path:?} in output"
    );
}

#[then(expr = "the rendered description should contain {string}")]
fn then_rendered_description_contains(world: &mut KanbusWorld, text: String) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains(&text), "expected {text:?} in output");
}

#[then(expr = "the rendered comments should contain {string}")]
fn then_rendered_comments_contains(world: &mut KanbusWorld, text: String) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(stdout.contains(&text), "expected {text:?} in output");
}

#[then(expr = "the rendered wiki should contain a link to issue {string}")]
fn then_rendered_wiki_has_issue_link(world: &mut KanbusWorld, identifier: String) {
    let stdout = world.stdout.as_ref().expect("stdout");
    assert!(
        stdout.contains(&identifier),
        "expected issue {identifier:?} in output"
    );
}

#[given("a Kanbus project with AI configured")]
fn given_project_with_ai_configured(world: &mut KanbusWorld) {
    std::env::set_var("KANBUS_NO_DAEMON", "1");
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    world.working_directory = Some(repo_path.clone());
    world.temp_dir = Some(temp_dir);
    run_cli(world, "kanbus init");
    assert_eq!(world.exit_code, Some(0));

    let config_path = repo_path.join(".kanbus.yml");
    let contents = fs::read_to_string(&config_path).expect("read config");
    let mut mapping: Mapping = serde_yaml::from_str(&contents).expect("parse config");
    let mut ai_block = Mapping::new();
    ai_block.insert(
        Value::String("provider".to_string()),
        Value::String("openai".to_string()),
    );
    ai_block.insert(
        Value::String("model".to_string()),
        Value::String("gpt-4o".to_string()),
    );
    mapping.insert(Value::String("ai".to_string()), Value::Mapping(ai_block));
    let yaml = serde_yaml::to_string(&mapping).expect("serialize config");
    fs::write(config_path, yaml).expect("write config");

    world.jira_unset_env_vars.push((
        String::from("KANBUS_TEST_AI_MOCK"),
        std::env::var("KANBUS_TEST_AI_MOCK").ok(),
    ));
    std::env::set_var("KANBUS_TEST_AI_MOCK", "1");
}

fn ai_call_count(world: &KanbusWorld) -> usize {
    let project_dir = load_project_dir(world);
    let log_path = project_dir.join(".cache").join("ai_calls.log");
    if log_path.exists() {
        fs::read_to_string(&log_path)
            .unwrap_or_default()
            .lines()
            .filter(|l| !l.is_empty())
            .count()
    } else {
        0
    }
}

#[then("the AI provider API should be called")]
fn then_ai_provider_api_called(world: &mut KanbusWorld) {
    let count = ai_call_count(world);
    assert!(count >= 1, "expected at least 1 API call, got {}", count);
    world.ai_call_count_after_first_render = Some(count);
}

#[then("the AI provider API should not be called")]
fn then_ai_provider_api_not_called(world: &mut KanbusWorld) {
    let count = ai_call_count(world);
    let expected = world.ai_call_count_after_first_render.unwrap_or(1);
    assert_eq!(
        count, expected,
        "expected no new API calls (count should be {}), got {}",
        expected, count
    );
}

#[then("a cached rendered file should exist")]
fn then_cached_rendered_file_exists(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let cache_dir = project_dir.join(".cache").join("wiki_render");
    assert!(
        cache_dir.exists(),
        "expected cache dir {} to exist",
        cache_dir.display()
    );
    let md_files: Vec<_> = fs::read_dir(&cache_dir)
        .unwrap_or_else(|_| panic!("read dir {}", cache_dir.display()))
        .filter_map(|e| e.ok())
        .filter(|e| e.path().extension().map_or(false, |ext| ext == "md"))
        .collect();
    assert!(
        !md_files.is_empty(),
        "expected at least one cached .md file in {}",
        cache_dir.display()
    );
}

#[then("the command should use the cache")]
fn then_command_uses_cache(world: &mut KanbusWorld) {
    let project_dir = load_project_dir(world);
    let log_path = project_dir.join(".cache").join("wiki_cache_hits.log");
    assert!(
        log_path.exists(),
        "expected cache hit log {} to exist",
        log_path.display()
    );
    let content = fs::read_to_string(&log_path).unwrap_or_default();
    let lines: Vec<_> = content.lines().filter(|l| !l.is_empty()).collect();
    assert!(
        !lines.is_empty(),
        "expected at least 1 cache hit, got {}",
        lines.len()
    );
}

#[then(expr = "the rendered wiki should contain a generated summary for {string}")]
fn then_rendered_wiki_has_generated_summary(world: &mut KanbusWorld, identifier: String) {
    let stdout = world.stdout.as_ref().expect("stdout");
    let expected = format!("Generated summary for {}", identifier);
    assert!(
        stdout.contains(&expected),
        "expected {expected:?} in output"
    );
}

#[given(expr = "a Kanbus project with wiki_directory set to {string}")]
fn given_project_with_wiki_directory(world: &mut KanbusWorld, value: String) {
    std::env::set_var("KANBUS_NO_DAEMON", "1");
    let temp_dir = TempDir::new().expect("tempdir");
    let repo_path = temp_dir.path().join("repo");
    fs::create_dir_all(&repo_path).expect("create repo dir");
    Command::new("git")
        .args(["init"])
        .current_dir(&repo_path)
        .output()
        .expect("git init failed");
    world.working_directory = Some(repo_path.clone());
    world.temp_dir = Some(temp_dir);
    run_cli(world, "kanbus init");
    assert_eq!(world.exit_code, Some(0));

    let config_path = repo_path.join(".kanbus.yml");
    let contents = fs::read_to_string(&config_path).expect("read config");
    let mut mapping: Mapping = serde_yaml::from_str(&contents).expect("parse config");
    mapping.insert(
        Value::String("wiki_directory".to_string()),
        Value::String(value.clone()),
    );
    let yaml = serde_yaml::to_string(&mapping).expect("serialize config");
    fs::write(config_path, yaml).expect("write config");
    world.wiki_directory = Some(value);
}

#[given(expr = "the Kanbus configuration has wiki_directory set to {string}")]
fn given_config_wiki_directory(world: &mut KanbusWorld, value: String) {
    let cwd = world.working_directory.as_ref().expect("working dir");
    let config_path = cwd.join(".kanbus.yml");
    let contents = fs::read_to_string(&config_path).expect("read config");
    let mut mapping: Mapping = serde_yaml::from_str(&contents).expect("parse config");
    mapping.insert(
        Value::String("wiki_directory".to_string()),
        Value::String(value),
    );
    let yaml = serde_yaml::to_string(&mapping).expect("serialize config");
    fs::write(config_path, yaml).expect("write config");
}

#[then(expr = "the wiki root should be {string}")]
fn then_wiki_root_is(world: &mut KanbusWorld, expected: String) {
    let cwd = world.working_directory.as_ref().expect("working dir");
    let wiki_path = cwd.join(&expected);
    assert!(
        wiki_path.exists(),
        "expected wiki root {expected} at {wiki_path:?}"
    );
}
