use cucumber::{given, then, when};

use crate::steps::initialization_steps::TaskulusWorld;
use taskulus::ids::format_issue_key;

#[given(expr = "an issue identifier {string}")]
fn given_issue_identifier(world: &mut TaskulusWorld, identifier: String) {
    world.generated_id = Some(identifier);
}

#[given(expr = "the display context is {string}")]
fn given_display_context(world: &mut TaskulusWorld, context: String) {
    world.display_context = Some(context);
}

#[when("I format the issue key")]
fn when_format_issue_key(world: &mut TaskulusWorld) {
    let identifier = world
        .generated_id
        .as_ref()
        .cloned()
        .unwrap_or_else(|| "".to_string());
    let context = world
        .display_context
        .as_ref()
        .map(|value| value == "project")
        .unwrap_or(false);
    let formatted = format_issue_key(&identifier, context);
    world.formatted_issue_key = Some(formatted);
}

#[then(expr = "the formatted key should be {string}")]
fn then_formatted_key_should_match(world: &mut TaskulusWorld, expected: String) {
    let formatted = world
        .formatted_issue_key
        .as_ref()
        .expect("formatted key present");
    assert_eq!(formatted, &expected);
}
