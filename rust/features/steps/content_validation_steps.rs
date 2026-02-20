use std::fs;

use cucumber::{gherkin::Step, given, then, when};

use kanbus::cli::run_from_args_with_output;
use kanbus::content_validation::{validate_code_blocks, CodeBlock};
use kanbus::error::KanbusError;

use crate::step_definitions::initialization_steps::KanbusWorld;

#[given(expr = "external validator {string} is not available")]
fn given_external_validator_not_available(_world: &mut KanbusWorld, tool: String) {
    std::env::set_var("KANBUS_TEST_EXTERNAL_TOOL_MISSING", tool);
}

#[given(expr = "external validator {string} is available and returns success")]
fn given_external_validator_available_success(world: &mut KanbusWorld, tool: String) {
    ensure_tool_stub(world, &tool, "exit 0\n");
}

#[given(expr = "external validator {string} is available and returns error {string}")]
fn given_external_validator_available_error(
    world: &mut KanbusWorld,
    tool: String,
    message: String,
) {
    let script = format!("echo \"{message}\" 1>&2\nexit 1\n");
    ensure_tool_stub(world, &tool, &script);
}

#[given(expr = "external validator {string} times out")]
fn given_external_validator_times_out(world: &mut KanbusWorld, tool: String) {
    std::env::set_var("KANBUS_TEST_EXTERNAL_TIMEOUT_MS", "50");
    ensure_tool_stub(world, &tool, "sleep 1\n");
}

#[when("I create an issue with description containing:")]
fn when_create_with_description(world: &mut KanbusWorld, step: &Step) {
    let description = step.docstring().expect("docstring").trim().to_string();
    let args_with_desc: Vec<String> = vec![
        "kanbus".to_string(),
        "create".to_string(),
        "Test".to_string(),
        "Issue".to_string(),
        "--description".to_string(),
        description,
    ];

    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");

    match run_from_args_with_output(args_with_desc, cwd.as_path()) {
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

#[when("I create an issue with --no-validate and description containing:")]
fn when_create_no_validate_with_description(world: &mut KanbusWorld, step: &Step) {
    let description = step.docstring().expect("docstring").trim().to_string();
    let args_with_desc: Vec<String> = vec![
        "kanbus".to_string(),
        "create".to_string(),
        "Test".to_string(),
        "Issue".to_string(),
        "--no-validate".to_string(),
        "--description".to_string(),
        description,
    ];

    let cwd = world
        .working_directory
        .as_ref()
        .expect("working directory not set");

    match run_from_args_with_output(args_with_desc, cwd.as_path()) {
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

#[when(expr = "I comment on {string} with text containing:")]
fn when_comment_with_text(world: &mut KanbusWorld, step: &Step, identifier: String) {
    let text = step.docstring().expect("docstring").trim().to_string();
    std::env::set_var("KANBUS_USER", "dev@example.com");
    let args: Vec<String> = vec![
        "kanbus".to_string(),
        "comment".to_string(),
        identifier,
        text,
    ];

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

#[when(expr = "I comment on {string} with --no-validate and text containing:")]
fn when_comment_no_validate_with_text(world: &mut KanbusWorld, step: &Step, identifier: String) {
    let text = step.docstring().expect("docstring").trim().to_string();
    std::env::set_var("KANBUS_USER", "dev@example.com");
    let args: Vec<String> = vec![
        "kanbus".to_string(),
        "comment".to_string(),
        identifier,
        "--no-validate".to_string(),
        text,
    ];

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

#[when(expr = "I update {string} with description containing:")]
fn when_update_with_description(world: &mut KanbusWorld, step: &Step, identifier: String) {
    let description = step.docstring().expect("docstring").trim().to_string();
    let args: Vec<String> = vec![
        "kanbus".to_string(),
        "update".to_string(),
        identifier,
        "--description".to_string(),
        description,
    ];

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

#[when("I validate code blocks directly:")]
fn when_validate_code_blocks_directly(world: &mut KanbusWorld, step: &Step) {
    let text = step.docstring().expect("docstring").trim();
    match validate_code_blocks(text) {
        Ok(()) => world.validation_error = None,
        Err(error) => world.validation_error = Some(error.to_string()),
    }
}

#[when(expr = "I validate external tool {string} directly with content:")]
fn when_validate_external_tool_directly(world: &mut KanbusWorld, tool: String, step: &Step) {
    let content = step.docstring().expect("docstring").trim().to_string();
    let block = CodeBlock {
        language: tool.clone(),
        content,
        start_line: 1,
    };
    let result = validate_external_tool(&block, &tool);
    match result {
        Ok(()) => world.validation_error = None,
        Err(error) => world.validation_error = Some(error.to_string()),
    }
}

#[then("the code block validation should succeed")]
fn then_code_block_validation_succeeds(world: &mut KanbusWorld) {
    assert!(world.validation_error.is_none());
}

#[then(expr = "the code block validation should fail with {string}")]
fn then_code_block_validation_fails(world: &mut KanbusWorld, message: String) {
    let error = world.validation_error.as_deref().unwrap_or("");
    assert!(
        error.contains(&message),
        "expected error to contain '{message}'"
    );
}

#[given("a registered user")]
fn given_registered_user(_world: &mut KanbusWorld) {}

#[when("they log in")]
fn when_they_log_in(_world: &mut KanbusWorld) {}

#[then("they see the dashboard")]
fn then_they_see_dashboard(_world: &mut KanbusWorld) {}

fn ensure_tool_stub(world: &mut KanbusWorld, tool: &str, script: &str) {
    if world.original_path.is_none() {
        world.original_path = Some(std::env::var("PATH").ok());
    }
    if world.external_tool_dir.is_none() {
        world.external_tool_dir =
            Some(tempfile::TempDir::new().expect("create external tool temp dir"));
    }
    let dir = world
        .external_tool_dir
        .as_ref()
        .expect("external tool dir")
        .path();
    let tool_path = dir.join(tool);
    fs::write(&tool_path, format!("#!/bin/sh\n{script}")).expect("write tool stub");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = fs::metadata(&tool_path)
            .expect("tool metadata")
            .permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&tool_path, permissions).expect("set tool permissions");
    }
    let new_path = match world.original_path.as_ref().and_then(|value| value.clone()) {
        Some(existing) => format!("{}:{}", dir.display(), existing),
        None => dir.display().to_string(),
    };
    std::env::set_var("PATH", new_path);
}

fn validate_external_tool(block: &CodeBlock, tool: &str) -> Result<(), KanbusError> {
    match tool {
        "mmdc" | "plantuml" | "d2" => {
            validate_code_blocks(&format!("```{}\n{}\n```", tool, block.content))
        }
        _ => Ok(()),
    }
}
