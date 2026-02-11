use cucumber::World;

mod step_definitions;

use step_definitions::initialization_steps::TaskulusWorld;

#[tokio::main]
async fn main() {
    TaskulusWorld::cucumber()
        .filter_run("tests/features", |feature, _, scenario| {
            let scenario_has_wip = scenario.tags.iter().any(|tag| tag == "wip");
            let feature_has_wip = feature.tags.iter().any(|tag| tag == "wip");
            !(scenario_has_wip || feature_has_wip)
        })
        .await;
}
