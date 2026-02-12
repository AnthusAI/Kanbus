Feature: Daemon error handling
  As a Taskulus maintainer
  I want daemon failures to surface with clear errors
  So that clients can recover safely

  Scenario: Daemon rejects incompatible protocol versions
    Given a Taskulus project with default configuration
    And the daemon is running with a socket
    When I send a daemon request with protocol version "2.0"
    Then the daemon response should include error code "protocol_version_mismatch"

  Scenario: Daemon list requires daemon enabled
    Given a Taskulus project with default configuration
    And daemon mode is disabled
    When I request a daemon index list
    Then the daemon request should fail with "daemon disabled"

  Scenario: Daemon status requires daemon enabled
    Given a Taskulus project with default configuration
    And daemon mode is disabled
    When I request a daemon status
    Then the daemon request should fail with "daemon disabled"

  Scenario: Daemon stop requires daemon enabled
    Given a Taskulus project with default configuration
    And daemon mode is disabled
    When I request a daemon shutdown
    Then the daemon request should fail with "daemon disabled"

  Scenario: Daemon rejects unsupported protocol versions
    Given a Taskulus project with default configuration
    And the daemon is running with a socket
    When I send a daemon request with protocol version "1.2"
    Then the daemon response should include error code "protocol_version_unsupported"

  Scenario: Daemon server direct handler rejects unsupported protocol versions
    Given a Taskulus project with default configuration
    When a daemon request with protocol version "1.2" is handled directly
    Then the daemon response should include error code "protocol_version_unsupported"

  Scenario: Daemon rejects unknown actions
    Given a Taskulus project with default configuration
    And the daemon is running with a socket
    When I send a daemon request with action "unknown.action"
    Then the daemon response should include error code "unknown_action"

  Scenario: Daemon handles invalid JSON payloads
    Given a Taskulus project with default configuration
    And the daemon is running with a socket
    When I send an invalid daemon payload
    Then the daemon response should include error code "internal_error"

  Scenario: Daemon ignores empty requests
    Given a Taskulus project with default configuration
    And the daemon is running with a socket
    When I open and close a daemon connection without data
    Then the daemon should still respond to ping

  Scenario: Daemon entry point can start and stop
    Given a Taskulus project with default configuration
    When the daemon entry point is started
    And I send a daemon shutdown request
    Then the daemon entry point should stop

  Scenario: Daemon entry point removes stale sockets
    Given a Taskulus project with default configuration
    And a stale daemon socket exists
    When the daemon entry point is started
    And I send a daemon shutdown request
    Then the daemon entry point should stop

  Scenario: Daemon client reports empty responses
    Given a Taskulus project with default configuration
    When I contact a daemon that returns an empty response
    Then the daemon request should fail with "empty daemon response"

  Scenario: Daemon status reports error responses
    Given a Taskulus project with default configuration
    When the daemon status response is an error
    Then the daemon request should fail with "daemon error"

  Scenario: Daemon stop reports error responses
    Given a Taskulus project with default configuration
    When the daemon stop response is an error
    Then the daemon request should fail with "daemon error"

  Scenario: Daemon list reports error responses
    Given a Taskulus project with default configuration
    When the daemon list response is an error
    Then the daemon request should fail with "daemon error"

  Scenario: Daemon list uses cache for repeated requests
    Given a Taskulus project with default configuration
    And issues "tsk-cache" exist
    And daemon mode is enabled
    And the daemon is running with a socket
    When I request a daemon index list
    And I request a daemon index list
    Then the daemon index list should include "tsk-cache"

  Scenario: Daemon list returns internal error when issue files are invalid
    Given a Taskulus project with default configuration
    And issues "tsk-bad" exist
    And daemon mode is enabled
    And the daemon is running with a socket
    And an issue file contains invalid JSON
    When I request a daemon index list
    Then the daemon request should fail

  Scenario: Daemon server returns internal error when issues directory is missing
    Given a Taskulus project with default configuration
    And the issues directory is missing
    When a daemon index list request is handled directly
    Then the daemon request should fail

  Scenario: Daemon list returns internal error when issues directory is missing
    Given a Taskulus project with default configuration
    And daemon mode is enabled
    And the daemon is running with a socket
    And the issues directory is missing
    When I request a daemon index list
    Then the daemon request should fail

  Scenario: Daemon list returns internal error when cache is unreadable
    Given a Taskulus project with default configuration
    And daemon mode is enabled
    And the daemon is running with a socket
    And the cache file is unreadable
    When I request a daemon index list
    Then the daemon request should fail

  Scenario: Daemon list returns empty when response omits issues
    Given a Taskulus project with default configuration
    And daemon mode is enabled
    And the daemon list response is missing issues
    When I request a daemon index list
    Then the daemon index list should be empty

  Scenario: Daemon spawn is invoked when socket is missing
    Given a Taskulus project with default configuration
    When the daemon is spawned for the project
    Then the daemon spawn should be recorded
