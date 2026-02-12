use cucumber::{given, then, when};

use taskulus::users::get_current_user;

use crate::step_definitions::initialization_steps::TaskulusWorld;

fn capture_original_env(world: &mut TaskulusWorld) {
    if world.original_taskulus_user.is_none() {
        world.original_taskulus_user = Some(std::env::var("TASKULUS_USER").ok());
    }
    if world.original_user_env.is_none() {
        world.original_user_env = Some(std::env::var("USER").ok());
    }
}

#[given(expr = "TASKULUS_USER is set to {string}")]
fn given_taskulus_user_set(world: &mut TaskulusWorld, value: String) {
    capture_original_env(world);
    std::env::set_var("TASKULUS_USER", value);
}

#[given("TASKULUS_USER is unset")]
fn given_taskulus_user_unset(world: &mut TaskulusWorld) {
    capture_original_env(world);
    std::env::remove_var("TASKULUS_USER");
}

#[given(expr = "USER is set to {string}")]
fn given_user_set(world: &mut TaskulusWorld, value: String) {
    capture_original_env(world);
    std::env::set_var("USER", value);
}

#[given("USER is unset")]
fn given_user_unset(world: &mut TaskulusWorld) {
    capture_original_env(world);
    std::env::remove_var("USER");
}

#[when("I resolve the current user")]
fn when_resolve_current_user(world: &mut TaskulusWorld) {
    world.current_user = Some(get_current_user());
}

#[then(expr = "the current user should be {string}")]
fn then_current_user_is(world: &mut TaskulusWorld, value: String) {
    assert_eq!(world.current_user.as_deref(), Some(value.as_str()));
}
