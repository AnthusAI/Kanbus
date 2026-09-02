Feature: Right now CLI command
  As a Kanbus user
  I want to list recently-updated issues with right-now summaries
  So that I can scan current status from the terminal

  Background:
    Given a Kanbus project with default configuration

  Scenario: Right now lists issues reverse-chronologically by updated_at
    Given an issue "kanbus-rn-a" exists with title "Oldest issue"
    And issue "kanbus-rn-a" has updated_at "2026-03-01T10:00:00+00:00"
    And an issue "kanbus-rn-b" exists with title "Middle issue"
    And issue "kanbus-rn-b" has updated_at "2026-03-01T11:00:00+00:00"
    And an issue "kanbus-rn-c" exists with title "Newest issue"
    And issue "kanbus-rn-c" has updated_at "2026-03-01T12:00:00+00:00"
    When I run "kanbus now"
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
    When I run "kanbus now --limit 2"
    Then the command should succeed
    And stdout should contain "kanbus-rn-l1"
    And stdout should contain "kanbus-rn-l2"
    And stdout should not contain "kanbus-rn-l3"

  Scenario: Flat output shows title and right-now summary
    Given an issue "kanbus-rn-sum" exists with title "Summary issue"
    And issue "kanbus-rn-sum" has right now summary "Working on the CLI command."
    When I run "kanbus now"
    Then the command should succeed
    And stdout should contain "Summary issue"
    And stdout should contain "Working on the CLI command."

  Scenario: Flat output shows placeholder when right-now summary is absent
    Given an issue "kanbus-rn-nosum" exists with title "No summary issue"
    When I run "kanbus now"
    Then the command should succeed
    And stdout should contain "No summary issue"
    And stdout should contain "(no right-now summary)"

  Scenario: Raw flat output shows titles only
    Given an issue "kanbus-rn-raw" exists with title "Raw issue"
    And issue "kanbus-rn-raw" has right now summary "Hidden summary."
    When I run "kanbus now --raw"
    Then the command should succeed
    And stdout should contain "Raw issue"
    And stdout should not contain "Hidden summary."
    And stdout should not contain "(no right-now summary)"

  Scenario: Tree output shows hierarchy with indentation
    Given an issue "kanbus-rn-init" of type "initiative" with status "open" and parent "kanbus-rn-missing" and title "Initiative root"
    And an issue "kanbus-rn-epic" of type "epic" with status "open" and parent "kanbus-rn-init" and title "Epic child"
    And an issue "kanbus-rn-task" of type "task" with status "open" and parent "kanbus-rn-epic" and title "Task leaf"
    And issue "kanbus-rn-init" has right now summary "Initiative summary."
    And issue "kanbus-rn-epic" has right now summary "Epic summary."
    And issue "kanbus-rn-task" has right now summary "Task summary."
    When I run "kanbus now --tree --collapsed"
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
    When I run "kanbus now --tree --expanded"
    Then the command should succeed
    And stdout should contain "[-] 2026-02-11T00:00:00.000Z  kanbus-rn-exp"
    And stdout should not contain "[+] 2026-02-11T00:00:00.000Z  kanbus-rn-exp"

  Scenario: Collapsed tree uses plus collapse markers
    Given an issue "kanbus-rn-col" exists with title "Collapsed node"
    And issue "kanbus-rn-col" has right now summary "Collapsed summary."
    When I run "kanbus now --tree --collapsed"
    Then the command should succeed
    And stdout should contain "[+] 2026-02-11T00:00:00.000Z  kanbus-rn-col"
    And stdout should not contain "[-] 2026-02-11T00:00:00.000Z  kanbus-rn-col"

  Scenario: JSON output is a flat array with expected fields
    Given an issue "kanbus-rn-json" exists with title "JSON issue"
    And issue "kanbus-rn-json" has right now summary "JSON summary."
    And issue "kanbus-rn-json" has updated_at "2026-03-01T12:34:56+00:00"
    When I run "kanbus now --json"
    Then the command should succeed
    And stdout should be valid JSON
    And the right now JSON output should have 1 item
    And the right now JSON item for "kanbus-rn-json" should include fields "id,title,type,status,updated_at,right_now_summary,parent"
    And the right now JSON item for "kanbus-rn-json" should have right_now_summary "JSON summary."

  Scenario: JSON output omits right_now_summary when raw
    Given an issue "kanbus-rn-jsonraw" exists with title "JSON raw issue"
    And issue "kanbus-rn-jsonraw" has right now summary "Omitted summary."
    When I run "kanbus now --json --raw"
    Then the command should succeed
    And stdout should be valid JSON
    And the right now JSON item for "kanbus-rn-jsonraw" should not include field "right_now_summary"

  Scenario: JSON tree output includes nested children
    Given an issue "kanbus-rn-jinit" of type "initiative" with status "open" and parent "kanbus-rn-jmissing" and title "JSON initiative"
    And an issue "kanbus-rn-jepic" of type "epic" with status "open" and parent "kanbus-rn-jinit" and title "JSON epic"
    And issue "kanbus-rn-jinit" has right now summary "Parent JSON summary."
    And issue "kanbus-rn-jepic" has right now summary "Child JSON summary."
    When I run "kanbus now --json --tree"
    Then the command should succeed
    And stdout should be valid JSON
    And the right now JSON tree should have root "kanbus-rn-jinit" with child "kanbus-rn-jepic"

  Scenario: Tie-break on identifier ascending when updated_at matches
    Given an issue "kanbus-rn-z" exists with title "Zulu issue"
    And issue "kanbus-rn-z" has updated_at "2026-03-01T12:00:00+00:00"
    And an issue "kanbus-rn-a-tie" exists with title "Alpha tie issue"
    And issue "kanbus-rn-a-tie" has updated_at "2026-03-01T12:00:00+00:00"
    When I run "kanbus now"
    Then the command should succeed
    And stdout should list "kanbus-rn-a-tie" before "kanbus-rn-z"

  Scenario: JSON output uses null for absent right-now summary
    Given an issue "kanbus-rn-null" exists with title "Null summary issue"
    When I run "kanbus now --json"
    Then the command should succeed
    And stdout should be valid JSON
    And the right now JSON item for "kanbus-rn-null" should have right_now_summary null
