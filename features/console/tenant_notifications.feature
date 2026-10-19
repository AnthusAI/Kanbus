@console-server
Feature: Tenant isolated console notifications
  As a console operator
  I want focus, search and notification streams scoped to the addressed tenant
  So that one tenant cannot change or observe another tenant's console state

  Scenario: Focus and search are isolated and survive restart
    Given a Kanbus project with default configuration
    Then focus and search state stays within its console tenant

  Scenario: Live delivery and replay are tenant scoped
    Given a Kanbus project with default configuration
    Then live and replayed notifications stay within their console tenant

  Scenario: Multi tenant console state requires an explicit tenant route
    Given a Kanbus project with default configuration
    Then root console notification routes require a tenant

  Scenario: Single tenant console behavior is retained
    Given a Kanbus project with default configuration
    Then single tenant console notifications retain their state and stream
