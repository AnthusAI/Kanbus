Feature: Lifecycle hooks
  As a project integrating with Kanbus
  I want first-class lifecycle hooks on command boundaries
  So I can run custom automation while preserving policy guidance behavior

  Background:
    Given a Kanbus project with default configuration
    And a lifecycle hook recorder script at "test-hooks/record-hook.sh"

  Scenario: after-hook executes on create, comment, and close
    Given the Kanbus hooks configuration is:
      """
      enabled: true
      run_in_beads_mode: true
      default_timeout_ms: 5000
      after:
        issue.create:
          - id: after-create
            command: ["./test-hooks/record-hook.sh", "after-create"]
            env:
              HOOK_LOG_PATH: "./hook.log"
        issue.comment:
          - id: after-comment
            command: ["./test-hooks/record-hook.sh", "after-comment"]
            env:
              HOOK_LOG_PATH: "./hook.log"
        issue.close:
          - id: after-close
            command: ["./test-hooks/record-hook.sh", "after-close"]
            env:
              HOOK_LOG_PATH: "./hook.log"
      """
    And an issue "kanbus-hook01" of type "task" with status "open"
    When I run "kanbus create \"Hook create task\" --type task"
    Then the command should succeed
    When I run "kanbus comment kanbus-hook01 \"Hook comment\""
    Then the command should succeed
    When I run "kanbus close kanbus-hook01"
    Then the command should succeed
    And hook log "hook.log" should contain "after-create"
    And hook log "hook.log" should contain "after-comment"
    And hook log "hook.log" should contain "after-close"

  Scenario: close with comment completes comment hooks before close hooks
    Given the Kanbus hooks configuration is:
      """
      enabled: true
      run_in_beads_mode: true
      default_timeout_ms: 5000
      before:
        issue.comment:
          - id: before-comment
            command: ["./test-hooks/record-hook.sh", "before-comment"]
            env: { HOOK_LOG_PATH: "./hook.log" }
        issue.close:
          - id: before-close
            command: ["./test-hooks/record-hook.sh", "before-close"]
            env: { HOOK_LOG_PATH: "./hook.log" }
      after:
        issue.comment:
          - id: after-comment
            command: ["./test-hooks/record-hook.sh", "after-comment"]
            env: { HOOK_LOG_PATH: "./hook.log" }
        issue.close:
          - id: after-close
            command: ["./test-hooks/record-hook.sh", "after-close"]
            env: { HOOK_LOG_PATH: "./hook.log" }
      """
    And an issue "kanbus-hook-order" of type "task" with status "open"
    When I run "kanbus close kanbus-hook-order --comment \"Done\""
    Then the command should succeed
    And hook log "hook.log" should equal:
      """
      before-comment
      after-comment
      before-close
      after-close
      """

  Scenario: before-hook blocks mutating operation on non-zero exit
    Given the Kanbus hooks configuration is:
      """
      enabled: true
      run_in_beads_mode: true
      default_timeout_ms: 5000
      before:
        issue.update:
          - id: before-update-fail
            command: ["sh", "-c", "cat >/dev/null; exit 7"]
      """
    And an issue "kanbus-hook02" of type "task" with status "open"
    When I run "kanbus update kanbus-hook02 --status in_progress"
    Then the command should fail with exit code 1
    And stderr should contain "blocking hook 'before-update-fail' failed"
    And issue "kanbus-hook02" should have status "open"

  Scenario: before-hook blocks mutating operation on timeout by default
    Given the Kanbus hooks configuration is:
      """
      enabled: true
      run_in_beads_mode: true
      default_timeout_ms: 5000
      before:
        issue.update:
          - id: before-update-timeout
            command: ["sh", "-c", "cat >/dev/null; sleep 1"]
            timeout_ms: 50
      """
    And an issue "kanbus-hook03" of type "task" with status "open"
    When I run "kanbus update kanbus-hook03 --status in_progress"
    Then the command should fail with exit code 1
    And stderr should contain "before-update-timeout"
    And stderr should contain "timed out"
    And issue "kanbus-hook03" should have status "open"

  Scenario: after-hook failure does not fail a successful command
    Given the Kanbus hooks configuration is:
      """
      enabled: true
      run_in_beads_mode: true
      default_timeout_ms: 5000
      after:
        issue.create:
          - id: after-create-fail
            command: ["sh", "-c", "cat >/dev/null; exit 5"]
      """
    When I run "kanbus create \"Hook observer failure\" --type task"
    Then the command should succeed
    And stderr should contain "Hook warning (issue.create/after/after-create-fail)"

  Scenario: read-operation hooks fire on show, list, and ready
    Given the Kanbus hooks configuration is:
      """
      enabled: true
      run_in_beads_mode: true
      default_timeout_ms: 5000
      after:
        issue.show:
          - id: after-show
            command: ["./test-hooks/record-hook.sh", "after-show"]
            env:
              HOOK_LOG_PATH: "./hook.log"
        issue.list:
          - id: after-list
            command: ["./test-hooks/record-hook.sh", "after-list"]
            env:
              HOOK_LOG_PATH: "./hook.log"
        issue.ready:
          - id: after-ready
            command: ["./test-hooks/record-hook.sh", "after-ready"]
            env:
              HOOK_LOG_PATH: "./hook.log"
      """
    And an issue "kanbus-hook04" of type "task" with status "open"
    When I run "kanbus show kanbus-hook04"
    Then the command should succeed
    When I run "kanbus list"
    Then the command should succeed
    When I run "kanbus ready"
    Then the command should succeed
    And hook log "hook.log" should contain "after-show"
    And hook log "hook.log" should contain "after-list"
    And hook log "hook.log" should contain "after-ready"

  Scenario: Beads-mode hook execution works when enabled
    Given a Kanbus project with beads compatibility enabled
    And a lifecycle hook recorder script at "test-hooks/record-hook.sh"
    Given the Kanbus hooks configuration is:
      """
      enabled: true
      run_in_beads_mode: true
      default_timeout_ms: 5000
      after:
        issue.create:
          - id: beads-after-create
            command: ["./test-hooks/record-hook.sh", "beads-after-create"]
            env:
              HOOK_LOG_PATH: "./hook.log"
      """
    When I run "kanbus --beads create \"Beads hook task\" --type task"
    Then the command should succeed
    And hook log "hook.log" should contain "beads-after-create"

  Scenario: policy guidance still emits via the built-in hook provider
    Given a policy file "list-guidance.policy" with content:
      """
      Feature: Hook-backed policy guidance

        Rule: list reminder
          Scenario: list reminder
            When listing issues
            Then suggest "Keep issue states current while planning."
      """
    And an issue "kanbus-hook05" of type "task" with status "open"
    When I run "kanbus list"
    Then the command should succeed
    And stderr should contain "GUIDANCE SUGGESTION: Keep issue states current while planning."

  Scenario: no-guidance suppresses policy guidance without disabling external hooks
    Given a policy file "list-guidance.policy" with content:
      """
      Feature: Hook-backed policy guidance

        Rule: list reminder
          Scenario: list reminder
            When listing issues
            Then suggest "Keep issue states current while planning."
      """
    And the Kanbus hooks configuration is:
      """
      enabled: true
      run_in_beads_mode: true
      default_timeout_ms: 5000
      after:
        issue.list:
          - id: external-after-list
            command: ["./test-hooks/record-hook.sh", "external-after-list"]
            env:
              HOOK_LOG_PATH: "./hook.log"
      """
    And an issue "kanbus-hook06" of type "task" with status "open"
    When I run "kanbus --no-guidance list"
    Then the command should succeed
    And stderr should not contain "GUIDANCE SUGGESTION"
    And hook log "hook.log" should contain "external-after-list"

  Scenario: global hook disable works with CLI and env controls
    Given the Kanbus hooks configuration is:
      """
      enabled: true
      run_in_beads_mode: true
      default_timeout_ms: 5000
      after:
        issue.create:
          - id: after-create-disabled
            command: ["./test-hooks/record-hook.sh", "after-create-disabled"]
            env:
              HOOK_LOG_PATH: "./hook.log"
      """
    When I run "kanbus --no-hooks create \"No hooks via flag\" --type task"
    Then the command should succeed
    And hook log "hook.log" should not contain "after-create-disabled"
    Given the environment variable KANBUS_NO_HOOKS is set to "1"
    When I run "kanbus create \"No hooks via env\" --type task"
    Then the command should succeed
    And hook log "hook.log" should not contain "after-create-disabled"

  Scenario: hooks list and validate provide first-class operability
    Given the Kanbus hooks configuration is:
      """
      enabled: true
      run_in_beads_mode: true
      default_timeout_ms: 5000
      after:
        issue.create:
          - id: list-validate-create
            command: ["./test-hooks/record-hook.sh", "list-validate-create"]
            env:
              HOOK_LOG_PATH: "./hook.log"
      """
    When I run "kanbus hooks list"
    Then the command should succeed
    And stdout should contain "[external] after issue.create list-validate-create"
    And stdout should contain "[built-in] after issue.list policy-guidance"
    When I run "kanbus hooks validate"
    Then the command should succeed
    And stdout should contain "Hook configuration is valid."

  Scenario: before-hook that never reads a large payload is killed at its timeout
    Given the Kanbus hooks configuration is:
      """
      enabled: true
      run_in_beads_mode: true
      default_timeout_ms: 5000
      before:
        issue.update:
          - id: before-update-never-reads
            command: ["sleep", "30"]
            timeout_ms: 300
      """
    And an issue "kanbus-hook-big" of type "task" with status "open"
    And issue "kanbus-hook-big" has description with 262144 characters
    When I run "kanbus update kanbus-hook-big --status in_progress"
    Then the command should fail with exit code 1
    And stderr should contain "before-update-never-reads"
    And stderr should contain "timed out"
    And issue "kanbus-hook-big" should have status "open"

  Scenario: before-hook that writes more than the pipe buffer to stderr still completes
    Given the Kanbus hooks configuration is:
      """
      enabled: true
      run_in_beads_mode: true
      default_timeout_ms: 5000
      before:
        issue.update:
          - id: before-update-noisy
            command: ["sh", "-c", "cat >/dev/null; head -c 262144 /dev/zero | tr '\\0' x >&2"]
      """
    And an issue "kanbus-hook-noisy" of type "task" with status "open"
    When I run "kanbus update kanbus-hook-noisy --status in_progress"
    Then the command should succeed
    And issue "kanbus-hook-noisy" should have status "in_progress"

  Scenario: before-hook whose background grandchild holds stderr open is bounded by its timeout
    Given the Kanbus hooks configuration is:
      """
      enabled: true
      run_in_beads_mode: true
      default_timeout_ms: 5000
      before:
        issue.update:
          - id: before-update-grandchild
            command: ["sh", "-c", "cat >/dev/null; (sleep 30 >&2 & echo $! > grandchild.pid); exit 0"]
            timeout_ms: 500
      """
    And an issue "kanbus-hook-grandchild" of type "task" with status "open"
    When I run "kanbus update kanbus-hook-grandchild --status in_progress"
    Then the command should fail with exit code 1
    And stderr should contain "before-update-grandchild"
    And stderr should contain "timed out after 500ms"
    And issue "kanbus-hook-grandchild" should have status "open"
    And the process recorded in "grandchild.pid" should not be running
