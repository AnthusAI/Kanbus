use cucumber::{given, then, when};

use kanbus::users::get_current_user;

use crate::step_definitions::initialization_steps::KanbusWorld;

fn capture_original_env(world: &mut KanbusWorld) {
    if world.original_kanbus_user.is_none() {
        world.original_kanbus_user = Some(std::env::var("KANBUS_USER").ok());
    }
    if world.original_user_env.is_none() {
        world.original_user_env = Some(std::env::var("USER").ok());
    }
}

#[given(expr = "KANBUS_USER is set to {string}")]
fn given_kanbus_user_set(world: &mut KanbusWorld, value: String) {
    capture_original_env(world);
    std::env::set_var("KANBUS_USER", value);
}

#[given("KANBUS_USER is unset")]
fn given_kanbus_user_unset(world: &mut KanbusWorld) {
    capture_original_env(world);
    std::env::remove_var("KANBUS_USER");
}

#[given(expr = "USER is set to {string}")]
fn given_user_set(world: &mut KanbusWorld, value: String) {
    capture_original_env(world);
    std::env::set_var("USER", value);
}

#[given("USER is unset")]
fn given_user_unset(world: &mut KanbusWorld) {
    capture_original_env(world);
    std::env::remove_var("USER");
}

#[when("I resolve the current user")]
fn when_resolve_current_user(world: &mut KanbusWorld) {
    world.current_user = Some(get_current_user());
}

#[then(expr = "the current user should be {string}")]
fn then_current_user_is(world: &mut KanbusWorld, value: String) {
    assert_eq!(world.current_user.as_deref(), Some(value.as_str()));
}
