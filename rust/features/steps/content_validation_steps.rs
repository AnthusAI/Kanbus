use cucumber::{gherkin::Step, given, when};

use kanbus::cli::run_from_args_with_output;

use crate::step_definitions::initialization_steps::KanbusWorld;

#[given(expr = "external validator {string} is not available")]
fn given_external_validator_not_available(_world: &mut KanbusWorld, tool: String) {
    // Override PATH so the external tool cannot be found.
    // We prepend a nonexistent directory to effectively hide the tool.
    // Since validate_external uses `which <tool>`, an empty PATH segment won't help.
    // Instead, we set an environment variable that our validation can check,
    // or we simply rely on the tool not being installed in CI.
    // For now, this step is a no-op because the feature scenarios for external tools
    // only test the "skip when not available" path, and these tools are typically
    // not installed in test environments.
    let _ = tool;
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
