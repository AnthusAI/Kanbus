@rust-only
Feature: Kanbus orchestration

  Scenario: Claiming the next ready issue emits JSON
    Given a Kanbus project with default configuration
    And an issue "kanbus-ready01" of type "task" with status "open"
    And an issue "kanbus-ready02" of type "task" with status "open"
    When I run "kanbus claim-next --ready --assignee worker-one --json"
    Then the command should succeed
    And stdout should contain "\"id\""
    And stdout should contain "\"assignee\""
    And stdout should contain "\"worker-one\""

  Scenario: Runs can be recorded and inspected
    Given a Kanbus project with default configuration
    And an issue "kanbus-run01" of type "task" with status "open"
    When I run "kanbus runs create kanbus-run01 --worker worker-one --json"
    Then the command should succeed
    And stdout should contain "\"run_id\""
    And stdout should contain "\"kanbus-run-"
    And stdout should contain "\"issue_id\""
    And stdout should contain "\"kanbus-run01\""
    When I run "kanbus runs list --json"
    Then the command should succeed
    And stdout should contain "\"kanbus-run01\""

  Scenario: Unsupported publish modes are rejected before work starts
    Given a Kanbus project with default configuration
    And an issue "kanbus-run01" of type "task" with status "open"
    And a local orchestration target repository
    And an orchestration workflow "workflow.md" with publish mode "pull-request"
    When I run the orchestration worker for issue "kanbus-run01" with workflow "workflow.md"
    Then the command should fail with exit code 1
    And stderr should contain "unsupported publish mode"

  Scenario: Workspace roots inside the Kanbus repository are rejected
    Given a Kanbus project with default configuration
    And an issue "kanbus-run01" of type "task" with status "open"
    And a local orchestration target repository
    And an orchestration workflow "workflow.md" with workspace root inside the Kanbus repository
    When I run the orchestration worker for issue "kanbus-run01" with workflow "workflow.md"
    Then the command should fail with exit code 1
    And stderr should contain "workspace root must be outside the Kanbus repository"

  Scenario: Worker branches outside the agent namespace are rejected
    Given a Kanbus project with default configuration
    And an issue "kanbus-run01" of type "task" with status "open"
    And a local orchestration target repository
    And an orchestration workflow "workflow.md" with worker branch pattern "experiment/{{ issue.identifier }}"
    When I run the orchestration worker for issue "kanbus-run01" with workflow "workflow.md"
    Then the command should fail with exit code 1
    And stderr should contain "worker branch must be under agent/"

  Scenario: Named workflow presets are resolved from the repository
    Given a Kanbus project with default configuration
    And an issue "kanbus-run01" of type "task" with status "open"
    And a local orchestration target repository
    And a repository orchestration workflow preset "call-criteria/poetry-upgrade"
    When I run the orchestration worker for issue "kanbus-run01" with workflow "call-criteria/poetry-upgrade"
    Then the command should succeed
    And stdout should contain "\"remote_branch\""

  Scenario: Missing named workflow presets fail clearly
    Given a Kanbus project with default configuration
    And an issue "kanbus-run01" of type "task" with status "open"
    And a local orchestration target repository
    When I run the orchestration worker for issue "kanbus-run01" with workflow "missing/workflow"
    Then the command should fail with exit code 1
    And stderr should contain "workflow preset not found"

  Scenario: Orchestrator runs a specific open ready issue
    Given a Kanbus project with default configuration
    And an issue "kanbus-run01" of type "task" with status "open"
    And an issue "kanbus-run02" of type "task" with status "open"
    And a local orchestration target repository
    And a repository orchestration workflow preset "call-criteria/poetry-upgrade"
    When I run "kanbus orchestrator run --workflow call-criteria/poetry-upgrade --once --max-concurrent 1 --issue kanbus-run02"
    Then the command should succeed
    And stdout should contain "\"issue_id\": \"kanbus-run02\""

  Scenario: Orchestrator rejects an explicit issue that is not open
    Given a Kanbus project with default configuration
    And an issue "kanbus-run01" of type "task" with status "in_progress"
    And a local orchestration target repository
    And a repository orchestration workflow preset "call-criteria/poetry-upgrade"
    When I run "kanbus orchestrator run --workflow call-criteria/poetry-upgrade --once --max-concurrent 1 --issue kanbus-run01"
    Then the command should fail with exit code 1
    And stderr should contain "explicit issue is not open"
