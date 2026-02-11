use cucumber::{given, then, when, World};

#[derive(Debug, Default, World)]
struct TaskulusWorld;

#[given("a placeholder precondition")]
async fn given_placeholder_precondition(_world: &mut TaskulusWorld) {}

#[when("a placeholder action occurs")]
async fn when_placeholder_action_occurs(_world: &mut TaskulusWorld) {}

#[then("a placeholder result is observed")]
async fn then_placeholder_result_is_observed(_world: &mut TaskulusWorld) {}

#[tokio::main]
async fn main() {
    TaskulusWorld::run("tests/features").await;
}
