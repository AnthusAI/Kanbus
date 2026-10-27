@console-server
Feature: Console network binding
  As a Kanbus user
  I want kbsc to listen on all interfaces by default
  So that I can open the board from other devices on my local network

  The CONSOLE_HOST environment variable selects the interface. Unset or empty
  means every interface (0.0.0.0), and `localhost` means 127.0.0.1. Any value
  that is not an IP address or `localhost` is a startup error; there is no
  fallback to another address.

  Reads are unauthenticated on the network, so writes (comments, status
  changes, assignments) are refused from any non-loopback peer. That refusal
  depends on the TCP peer address, which cannot be forged from within a
  same-host scenario, so it is covered by the Rust-level tests described in
  issue_write_controls.feature
  (`require_loopback_allows_127_0_0_1_and_refuses_other_addresses` and
  `post_issue_comment_root_refuses_a_non_loopback_caller`).

  Scenario: Default binds all interfaces
    Given a Kanbus project with default configuration
    Then kbsc started without CONSOLE_HOST listens on "0.0.0.0"

  Scenario: Loopback only when requested
    Given a Kanbus project with default configuration
    Then kbsc started with CONSOLE_HOST "127.0.0.1" listens on "127.0.0.1"

  Scenario: Localhost means the loopback address
    Given a Kanbus project with default configuration
    Then kbsc started with CONSOLE_HOST "localhost" listens on "127.0.0.1"

  Scenario: Invalid host is a startup error
    Given a Kanbus project with default configuration
    Then kbsc started with CONSOLE_HOST "not-an-ip" exits with an error naming "not-an-ip"
