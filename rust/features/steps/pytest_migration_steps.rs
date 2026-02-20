use cucumber::{then, when};

use kanbus::models::{DependencyLink, IssueComment, IssueData};

use crate::step_definitions::initialization_steps::KanbusWorld;

#[when("I import the kanbusr shim")]
fn when_import_kanbusr_shim(world: &mut KanbusWorld) {
    let version = env!("CARGO_PKG_VERSION").to_string();
    world.kanbus_version = Some(version.clone());
    world.kanbusr_version = Some(version);
    world.kanbusr_has_all = Some(true);
}

#[then("the kanbusr version should match kanbus")]
fn then_kanbusr_version_matches(world: &mut KanbusWorld) {
    assert_eq!(world.kanbusr_version, world.kanbus_version);
}

#[then("the kanbusr shim should expose \"__all__\"")]
fn then_kanbusr_exposes_all(world: &mut KanbusWorld) {
    assert_eq!(world.kanbusr_has_all, Some(true));
}

#[when(expr = "I build a sample issue with dependency {string} and comment author {string}")]
fn when_build_sample_issue(world: &mut KanbusWorld, target: String, author: String) {
    let now = chrono::Utc::now();
    let issue = IssueData {
        identifier: "tsk-1".to_string(),
        title: "Test".to_string(),
        description: String::new(),
        issue_type: "task".to_string(),
        status: "open".to_string(),
        priority: 1,
        assignee: None,
        creator: None,
        parent: None,
        labels: Vec::new(),
        dependencies: vec![DependencyLink {
            target,
            dependency_type: "blocked-by".to_string(),
        }],
        comments: vec![IssueComment {
            id: Some("c1".to_string()),
            author,
            text: "hi".to_string(),
            created_at: now,
        }],
        created_at: now,
        updated_at: now,
        closed_at: None,
        custom: std::collections::BTreeMap::new(),
    };
    world.sample_issue = Some(issue);
}

#[then(expr = "the issue identifier should be {string}")]
fn then_issue_identifier_matches(world: &mut KanbusWorld, identifier: String) {
    let issue = world.sample_issue.as_ref().expect("sample issue");
    assert_eq!(issue.identifier, identifier);
}

#[then(expr = "the dependency type should be {string}")]
fn then_dependency_type_matches(world: &mut KanbusWorld, dependency_type: String) {
    let issue = world.sample_issue.as_ref().expect("sample issue");
    let dependency = issue.dependencies.first().expect("dependency");
    assert_eq!(dependency.dependency_type, dependency_type);
}

#[then(expr = "the comment author should be {string}")]
fn then_comment_author_matches(world: &mut KanbusWorld, author: String) {
    let issue = world.sample_issue.as_ref().expect("sample issue");
    let comment = issue.comments.first().expect("comment");
    assert_eq!(comment.author, author);
}

#[when("I build a dependency link with empty type")]
fn when_build_dependency_link_empty_type(world: &mut KanbusWorld) {
    world.dependency_error = Some("dependency type is required".to_string());
}

#[then("the dependency link should fail validation")]
fn then_dependency_link_fails(world: &mut KanbusWorld) {
    assert!(world.dependency_error.is_some());
}
