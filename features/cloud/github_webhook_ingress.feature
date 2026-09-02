@cloud
Feature: GitHub webhook ingress
  As the Kanbus cloud sync pipeline
  I want GitHub push webhooks to identify tenants from the URL path
  So that GitHub can deliver pushes without custom Kanbus headers

  Background:
    Given the GitHub webhook secret is "test-secret"
    And the sync queue URL is "https://example.queue/url"

  Scenario: Valid signed push to path-scoped webhook URL queues tenant sync
    Given a signed GitHub push payload for account "acct" and project "proj"
    When the webhook handler receives the push at "/internal/webhooks/github/acct/proj"
    Then the webhook response status should be 202
    And the webhook response body should contain "queued"
    And the sync queue should receive a message for account "acct" and project "proj"

  Scenario: Missing account path segment returns client error
    Given a signed GitHub push payload for account "acct" and project "proj"
    When the webhook handler receives the push at "/internal/webhooks/github//proj"
    Then the webhook response status should be 400
    And the webhook response body should contain "missing"

  Scenario: Invalid project path segment returns client error
    Given a signed GitHub push payload for account "acct" and project "bad@proj"
    When the webhook handler receives the push at "/internal/webhooks/github/acct/bad@proj"
    Then the webhook response status should be 400
    And the webhook response body should contain "invalid tenant"

  Scenario: Invalid signature returns unauthorized
    Given an unsigned GitHub push payload for account "acct" and project "proj"
    When the webhook handler receives the push at "/internal/webhooks/github/acct/proj"
    Then the webhook response status should be 401
    And the webhook response body should contain "invalid signature"

  Scenario: Non-push GitHub event is ignored
    Given a signed GitHub push payload for account "acct" and project "proj"
    And the GitHub event type is "ping"
    When the webhook handler receives the push at "/internal/webhooks/github/acct/proj"
    Then the webhook response status should be 202
    And the webhook response body should contain "ignored"

  Scenario: GitHub-realistic delivery without Kanbus headers queues sync
    Given a signed GitHub push payload without Kanbus headers for account "anthus" and project "kanbus"
    When the webhook handler receives the push at "/internal/webhooks/github/anthus/kanbus"
    Then the webhook response status should be 202
    And the sync queue should receive a message for account "anthus" and project "kanbus"

  Scenario: Flat webhook URL without path segments is rejected
    Given a signed GitHub push payload for account "acct" and project "proj"
    When the webhook handler receives the push at "/internal/webhooks/github"
    Then the webhook response status should be 400
    And the webhook response body should contain "missing"
