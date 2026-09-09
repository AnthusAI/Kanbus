Feature: Right now CLI command
  As a Kanbus user
  I want to list recently-updated issues with right-now summaries
  So that I can scan current status from the terminal

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"

  Scenario: Right now lists issues reverse-chronologically by updated_at
    Given an issue "kanbus-rn-a" exists with title "Oldest issue"
    And issue "kanbus-rn-a" has updated_at "2026-03-01T10:00:00+00:00"
    And an issue "kanbus-rn-b" exists with title "Middle issue"
    And issue "kanbus-rn-b" has updated_at "2026-03-01T11:00:00+00:00"
    And an issue "kanbus-rn-c" exists with title "Newest issue"
    And issue "kanbus-rn-c" has updated_at "2026-03-01T12:00:00+00:00"
    When I run "kanbus now --status all"
    Then the command should succeed
    And stdout should list "kanbus-rn-c" before "kanbus-rn-b"
    And stdout should list "kanbus-rn-b" before "kanbus-rn-a"

  Scenario: Right now limit truncates output
    Given an issue "kanbus-rn-l1" exists with title "Limit one"
    And issue "kanbus-rn-l1" has updated_at "2026-03-01T12:00:00+00:00"
    And an issue "kanbus-rn-l2" exists with title "Limit two"
    And issue "kanbus-rn-l2" has updated_at "2026-03-01T11:00:00+00:00"
    And an issue "kanbus-rn-l3" exists with title "Limit three"
    And issue "kanbus-rn-l3" has updated_at "2026-03-01T10:00:00+00:00"
    When I run "kanbus now --status all --limit 2"
    Then the command should succeed
    And stdout should contain "kanbus-rn-l1"
    And stdout should contain "kanbus-rn-l2"
    And stdout should not contain "kanbus-rn-l3"

  Scenario: Default tree output is YAML with type and priority
    Given an issue "kanbus-rn-ytree" of type "initiative" with status "open" and parent "kanbus-rn-missing" and title "YAML tree root"
    And an issue "kanbus-rn-ychild" of type "epic" with status "open" and parent "kanbus-rn-ytree" and title "YAML tree child"
    And issue "kanbus-rn-ytree" has right now summary "Parent YAML summary."
    And issue "kanbus-rn-ychild" has right now summary "Child YAML summary."
    When I run "kanbus now --status all"
    Then the command should succeed
    And stdout should be valid YAML
    And the right now YAML tree should have root "kanbus-rn-ytree" with child "kanbus-rn-ychild"
    And the right now YAML tree item for "kanbus-rn-ytree" should include fields "id,title,type,status,priority,updated_at,right_now_summary,children"
    And the right now YAML tree item for "kanbus-rn-ytree" should have type "initiative"
    And the right now YAML tree item for "kanbus-rn-ytree" should have priority 2

  Scenario: Flat list output is YAML with type and priority
    Given an issue "kanbus-rn-yflat" of type "task" with status "open" and title "YAML flat issue"
    And issue "kanbus-rn-yflat" has right now summary "Flat YAML summary."
    When I run "kanbus now --status all --list"
    Then the command should succeed
    And stdout should be valid YAML
    And the right now YAML output should have 1 item
    And the right now YAML item for "kanbus-rn-yflat" should include fields "id,title,type,status,priority,updated_at,right_now_summary,parent"
    And the right now YAML item for "kanbus-rn-yflat" should have right_now_summary "Flat YAML summary."

  Scenario: Flat output JIT-generates a missing right-now summary
    Given an issue "kanbus-rn-nosum" exists with title "No summary issue"
    And mock AI is enabled
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"
    When I run "kanbus now --status all --list"
    Then the command should succeed
    And stdout should be valid YAML
    And the right now YAML item for "kanbus-rn-nosum" should have a non-empty right_now_summary
    And issue "kanbus-rn-nosum" should have a non-empty right now summary

  Scenario: Raw flat output omits right_now_summary
    Given an issue "kanbus-rn-raw" exists with title "Raw issue"
    And issue "kanbus-rn-raw" has right now summary "Hidden summary."
    When I run "kanbus now --status all --list --raw"
    Then the command should succeed
    And stdout should be valid YAML
    And the right now YAML item for "kanbus-rn-raw" should not include field "right_now_summary"

  Scenario: Text flat output shows title and right-now summary
    Given an issue "kanbus-rn-sum" exists with title "Summary issue"
    And issue "kanbus-rn-sum" has right now summary "Working on the CLI command."
    When I run "kanbus now --status all --list --text"
    Then the command should succeed
    And stdout should contain "Summary issue"
    And stdout should contain "Working on the CLI command."

  Scenario: Text tree output shows hierarchy with indentation
    Given an issue "kanbus-rn-init" of type "initiative" with status "open" and parent "kanbus-rn-missing" and title "Initiative root"
    And an issue "kanbus-rn-epic" of type "epic" with status "open" and parent "kanbus-rn-init" and title "Epic child"
    And an issue "kanbus-rn-task" of type "task" with status "open" and parent "kanbus-rn-epic" and title "Task leaf"
    And issue "kanbus-rn-init" has right now summary "Initiative summary."
    And issue "kanbus-rn-epic" has right now summary "Epic summary."
    And issue "kanbus-rn-task" has right now summary "Task summary."
    When I run "kanbus now --status all --collapsed --text"
    Then the command should succeed
    And stdout should contain "[+] 2026-02-11T00:00:00.000Z  kanbus-rn-init"
    And stdout should contain "  [+] 2026-02-11T00:00:00.000Z  kanbus-rn-epic"
    And stdout should contain "    [+] 2026-02-11T00:00:00.000Z  kanbus-rn-task"
    And stdout should contain "Initiative summary."
    And stdout should contain "Epic summary."
    And stdout should contain "Task summary."

  Scenario: Expanded tree uses minus collapse markers
    Given an issue "kanbus-rn-exp" exists with title "Expanded node"
    And issue "kanbus-rn-exp" has right now summary "Expanded summary."
    When I run "kanbus now --status all --expanded --text"
    Then the command should succeed
    And stdout should contain "[-] 2026-02-11T00:00:00.000Z  kanbus-rn-exp"
    And stdout should not contain "[+] 2026-02-11T00:00:00.000Z  kanbus-rn-exp"

  Scenario: Collapsed tree uses plus collapse markers
    Given an issue "kanbus-rn-col" exists with title "Collapsed node"
    And issue "kanbus-rn-col" has right now summary "Collapsed summary."
    When I run "kanbus now --status all --collapsed --text"
    Then the command should succeed
    And stdout should contain "[+] 2026-02-11T00:00:00.000Z  kanbus-rn-col"
    And stdout should not contain "[-] 2026-02-11T00:00:00.000Z  kanbus-rn-col"

  Scenario: JSON output is a flat array with expected fields
    Given an issue "kanbus-rn-json" exists with title "JSON issue"
    And issue "kanbus-rn-json" has right now summary "JSON summary."
    And issue "kanbus-rn-json" has updated_at "2026-03-01T12:34:56+00:00"
    When I run "kanbus now --status all --json --list"
    Then the command should succeed
    And stdout should be valid JSON
    And the right now JSON output should have 1 item
    And the right now JSON item for "kanbus-rn-json" should include fields "id,title,type,status,priority,updated_at,right_now_summary,parent"
    And the right now JSON item for "kanbus-rn-json" should have right_now_summary "JSON summary."

  Scenario: JSON output omits right_now_summary when raw
    Given an issue "kanbus-rn-jsonraw" exists with title "JSON raw issue"
    And issue "kanbus-rn-jsonraw" has right now summary "Omitted summary."
    When I run "kanbus now --status all --json --raw"
    Then the command should succeed
    And stdout should be valid JSON
    And the right now JSON item for "kanbus-rn-jsonraw" should not include field "right_now_summary"

  Scenario: JSON tree output includes nested children
    Given an issue "kanbus-rn-jinit" of type "initiative" with status "open" and parent "kanbus-rn-jmissing" and title "JSON initiative"
    And an issue "kanbus-rn-jepic" of type "epic" with status "open" and parent "kanbus-rn-jinit" and title "JSON epic"
    And issue "kanbus-rn-jinit" has right now summary "Parent JSON summary."
    And issue "kanbus-rn-jepic" has right now summary "Child JSON summary."
    When I run "kanbus now --status all --json"
    Then the command should succeed
    And stdout should be valid JSON
    And the right now JSON tree should have root "kanbus-rn-jinit" with child "kanbus-rn-jepic"
    And the right now JSON tree item for "kanbus-rn-jinit" should include fields "id,title,type,status,priority,updated_at,right_now_summary,children"
    And the right now JSON tree item for "kanbus-rn-jepic" should include fields "id,title,type,status,priority,updated_at,right_now_summary,children"

  Scenario: Tie-break on identifier ascending when updated_at matches
    Given an issue "kanbus-rn-z" exists with title "Zulu issue"
    And issue "kanbus-rn-z" has updated_at "2026-03-01T12:00:00+00:00"
    And an issue "kanbus-rn-a-tie" exists with title "Alpha tie issue"
    And issue "kanbus-rn-a-tie" has updated_at "2026-03-01T12:00:00+00:00"
    When I run "kanbus now --status all"
    Then the command should succeed
    And stdout should list "kanbus-rn-a-tie" before "kanbus-rn-z"

  Scenario: JSON output JIT-generates a missing right-now summary
    Given an issue "kanbus-rn-null" exists with title "Null summary issue"
    And mock AI is enabled
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-4o-mini"
    When I run "kanbus now --status all --json --list"
    Then the command should succeed
    And stdout should be valid JSON
    And the right now JSON item for "kanbus-rn-null" should have a non-empty right_now_summary

  Scenario: Selected issue lists only that issue
    Given an issue "kanbus-rn-sel-a" exists with title "Selected alpha"
    And issue "kanbus-rn-sel-a" has right now summary "Alpha is selected."
    And an issue "kanbus-rn-sel-b" exists with title "Selected beta"
    And issue "kanbus-rn-sel-b" has right now summary "Beta is ignored."
    When I run "kanbus now kanbus-rn-sel-a"
    Then the command should succeed
    And stdout should contain "kanbus-rn-sel-a"
    And stdout should contain "Alpha is selected."
    And stdout should not contain "kanbus-rn-sel-b"
    And stdout should not contain "Beta is ignored."

  Scenario: Multiple selected issues list only those issues
    Given an issue "kanbus-rn-multi-a" exists with title "Multi alpha"
    And an issue "kanbus-rn-multi-b" exists with title "Multi beta"
    And an issue "kanbus-rn-multi-c" exists with title "Multi gamma"
    When I run "kanbus now kanbus-rn-multi-a kanbus-rn-multi-c"
    Then the command should succeed
    And stdout should contain "kanbus-rn-multi-a"
    And stdout should contain "kanbus-rn-multi-c"
    And stdout should not contain "kanbus-rn-multi-b"

  Scenario: Recursive includes descendants of the selected issue
    Given an issue "kanbus-rn-rec-init" of type "initiative" with status "open" and parent "kanbus-rn-missing" and title "Recursive initiative"
    And an issue "kanbus-rn-rec-epic" of type "epic" with status "open" and parent "kanbus-rn-rec-init" and title "Recursive epic"
    And an issue "kanbus-rn-rec-task" of type "task" with status "open" and parent "kanbus-rn-rec-epic" and title "Recursive task"
    And an issue "kanbus-rn-rec-other" exists with title "Unrelated task"
    When I run "kanbus now kanbus-rn-rec-init"
    Then the command should succeed
    And stdout should contain "kanbus-rn-rec-init"
    And stdout should contain "kanbus-rn-rec-epic"
    And stdout should contain "kanbus-rn-rec-task"
    And stdout should not contain "kanbus-rn-rec-other"

  Scenario: Without recursive descendants are omitted
    Given an issue "kanbus-rn-flat-init" of type "initiative" with status "open" and parent "kanbus-rn-missing" and title "Flat initiative"
    And an issue "kanbus-rn-flat-epic" of type "epic" with status "open" and parent "kanbus-rn-flat-init" and title "Flat epic"
    When I run "kanbus now kanbus-rn-flat-init --no-recursive"
    Then the command should succeed
    And stdout should contain "kanbus-rn-flat-init"
    And stdout should not contain "kanbus-rn-flat-epic"

  Scenario: Recursive tree nests descendants under the selected issue
    Given an issue "kanbus-rn-tree-init" of type "initiative" with status "open" and parent "kanbus-rn-missing" and title "Tree initiative"
    And an issue "kanbus-rn-tree-epic" of type "epic" with status "open" and parent "kanbus-rn-tree-init" and title "Tree epic"
    When I run "kanbus now kanbus-rn-tree-init --collapsed --text"
    Then the command should succeed
    And stdout should contain "[+] 2026-02-11T00:00:00.000Z  kanbus-rn-tree-init"
    And stdout should contain "  [+] 2026-02-11T00:00:00.000Z  kanbus-rn-tree-epic"

  Scenario: All flag lists issues beyond the default limit
    Given 31 issues exist with identifier prefix "kanbus-rn-many"
    When I run "kanbus now --status all --all"
    Then the command should succeed
    And stdout should contain "kanbus-rn-many-31"
    When I run "kanbus now --status all"
    Then the command should succeed
    And stdout should not contain "kanbus-rn-many-31"

  Scenario: All cannot combine with limit
    When I run "kanbus now --status all --all --limit 2"
    Then the command should fail
    And stderr should contain "cannot combine --all with --limit"

  Scenario: All cannot combine with issue identifiers
    Given an issue "kanbus-rn-allid" exists with title "All with id"
    When I run "kanbus now --status all --all kanbus-rn-allid"
    Then the command should fail
    And stderr should contain "cannot combine --all with issue identifiers"

  Scenario: No-recursive requires issue identifiers
    When I run "kanbus now --status all --no-recursive"
    Then the command should fail
    And stderr should contain "--no-recursive requires one or more issue identifiers"

  Scenario: Selected missing issue fails
    When I run "kanbus now kanbus-rn-missing"
    Then the command should fail
    And stderr should contain "not found"
