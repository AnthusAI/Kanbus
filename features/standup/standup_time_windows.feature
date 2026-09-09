@wip
Feature: Standup time windows (rolling and calendar)
  As a Kanbus user generating standup reports
  I want lookback windows that match how teams actually run standups
  So that Yesterday and Momentum signals reflect business days, overnight work, and profile intent

  Standup signal sections (Yesterday, Likely questions staleness, Momentum, Risks) evaluate
  issue timestamps and event `occurred_at` values against a resolved time window anchored at
  **report time**. Report time defaults to current UTC; scenarios pin it with the Given step
  below so overnight and weekday boundaries are deterministic.

  Configuration (`.kanbus.yml` under `standup`):
  - `window_mode`: `rolling` | `calendar` (global default: `rolling`)
  - `lookback_hours`: positive integer; supported values in specs: `8`, `24` (global default: `24`)
  - `skip_weekends`: boolean (global default: `false`)

  Profile defaults (apply when the profile is selected and no explicit override is set):
  - **meeting-script**: `window_mode: calendar`, `skip_weekends: true`
  - **director-brief**: `window_mode: rolling`, `lookback_hours: 24`

  Window semantics (observable):
  - **rolling**: an timestamp qualifies when it is on or after
    `report_time - lookback_hours` and on or before `report_time` (continuous hours).
  - **calendar** with `skip_weekends: false`: **Yesterday** spans the calendar day immediately
    before the report-time calendar date (UTC), from 00:00:00 through 23:59:59.999 on that date.
  - **calendar** with `skip_weekends: true`: **Yesterday** spans the previous **business day**
    — the most recent Monday–Friday calendar day strictly before the report-time calendar date.
    Saturday and Sunday closes do not qualify for Yesterday on a Monday report; Friday closes do.
    On Saturday or Sunday reports, Yesterday spans the preceding Friday.
  - Staleness signals (Likely questions, Risks) continue to compare `updated_at` against
    `lookback_hours` relative to report time regardless of `window_mode`.

  JSON contract (both runtimes, `--json`):
  - Top-level fields `window_mode`, `lookback_hours`, and `skip_weekends` record the resolved
    values used for the invocation (after profile defaults and configuration overrides).

  Dual-runtime: scenarios in this file require identical observable behavior in Python behave
  and Rust cucumber before the `@wip` tag is removed.

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-5.6-luna"

  Scenario: Meeting-script default resolves calendar window with skip weekends
    Given standup report time is "2026-09-08T09:00:00Z"
    And an issue "kanbus-tw-ms-def" exists with status "in_progress"
    And issue "kanbus-tw-ms-def" has right now summary "Default calendar window work."
    When I run "kanbus standup kanbus-tw-ms-def --profile meeting-script --json"
    Then the command should succeed
    And the standup JSON output should record window_mode "calendar"
    And the standup JSON output should record skip_weekends true

  Scenario: Director-brief default resolves rolling twenty-four hour window
    Given standup report time is "2026-09-08T09:00:00Z"
    And an issue "kanbus-tw-db-def" exists with status "in_progress"
    And issue "kanbus-tw-db-def" has right now summary "Default rolling window work."
    When I run "kanbus standup kanbus-tw-db-def --profile director-brief --json"
    Then the command should succeed
    And the standup JSON output should record window_mode "rolling"
    And the standup JSON output should record lookback_hours 24
    And the standup JSON output should record skip_weekends false

  Scenario: Explicit rolling eight hour window includes overnight closure within lookback
    Given standup report time is "2026-09-08T09:00:00Z"
    And standup window mode is rolling
    And standup lookback hours is 8
    And an issue "kanbus-tw-roll-in" exists with status "closed"
    And issue "kanbus-tw-roll-in" has closed_at at "2026-09-08T02:00:00Z"
    And issue "kanbus-tw-roll-in" has right now summary "Overnight rolling close."
    When I run "kanbus standup kanbus-tw-roll-in --profile director-brief"
    Then the command should succeed
    And the standup report section "Momentum" should mention "Overnight rolling close"

  Scenario: Explicit rolling eight hour window excludes closure before overnight lookback
    Given standup report time is "2026-09-08T09:00:00Z"
    And standup window mode is rolling
    And standup lookback hours is 8
    And an issue "kanbus-tw-roll-out" exists with status "closed"
    And issue "kanbus-tw-roll-out" has closed_at at "2026-09-07T00:30:00Z"
    And issue "kanbus-tw-roll-out" has right now summary "Too early for eight hour window."
    When I run "kanbus standup kanbus-tw-roll-out --profile director-brief"
    Then the command should succeed
    And the standup report section "Momentum" should not mention "Too early for eight hour window"

  Scenario: Monday meeting-script calendar skip weekends Yesterday includes Friday not Sunday
    Given standup report time is "2026-09-08T09:00:00Z"
    And an issue "kanbus-tw-mon-fri" exists with status "closed"
    And issue "kanbus-tw-mon-fri" has closed_at at "2026-09-05T17:00:00Z"
    And issue "kanbus-tw-mon-fri" has right now summary "Friday calendar yesterday."
    And an issue "kanbus-tw-mon-sun" exists with status "closed"
    And issue "kanbus-tw-mon-sun" has closed_at at "2026-09-07T15:00:00Z"
    And issue "kanbus-tw-mon-sun" has right now summary "Sunday calendar excluded."
    When I run "kanbus standup kanbus-tw-mon-fri kanbus-tw-mon-sun --profile meeting-script"
    Then the command should succeed
    And the standup report section "Yesterday" should mention "Friday calendar yesterday"
    And the standup report section "Yesterday" should not mention "Sunday calendar excluded"

  Scenario: Friday meeting-script calendar skip weekends Yesterday includes Thursday not Wednesday
    Given standup report time is "2026-09-12T09:00:00Z"
    And an issue "kanbus-tw-fri-thu" exists with status "closed"
    And issue "kanbus-tw-fri-thu" has closed_at at "2026-09-11T16:00:00Z"
    And issue "kanbus-tw-fri-thu" has right now summary "Thursday calendar yesterday."
    And an issue "kanbus-tw-fri-wed" exists with status "closed"
    And issue "kanbus-tw-fri-wed" has closed_at at "2026-09-10T16:00:00Z"
    And issue "kanbus-tw-fri-wed" has right now summary "Wednesday calendar excluded."
    When I run "kanbus standup kanbus-tw-fri-thu kanbus-tw-fri-wed --profile meeting-script"
    Then the command should succeed
    And the standup report section "Yesterday" should mention "Thursday calendar yesterday"
    And the standup report section "Yesterday" should not mention "Wednesday calendar excluded"

  Scenario: Saturday meeting-script calendar skip weekends Yesterday spans preceding Friday
    Given standup report time is "2026-09-13T10:00:00Z"
    And an issue "kanbus-tw-sat-fri" exists with status "closed"
    And issue "kanbus-tw-sat-fri" has closed_at at "2026-09-12T18:00:00Z"
    And issue "kanbus-tw-sat-fri" has right now summary "Friday before Saturday report."
    And an issue "kanbus-tw-sat-thu" exists with status "closed"
    And issue "kanbus-tw-sat-thu" has closed_at at "2026-09-11T18:00:00Z"
    And issue "kanbus-tw-sat-thu" has right now summary "Thursday before Saturday report."
    When I run "kanbus standup kanbus-tw-sat-fri kanbus-tw-sat-thu --profile meeting-script"
    Then the command should succeed
    And the standup report section "Yesterday" should mention "Friday before Saturday report"
    And the standup report section "Yesterday" should not mention "Thursday before Saturday report"

  Scenario: Sunday meeting-script calendar skip weekends Yesterday spans preceding Friday
    Given standup report time is "2026-09-14T10:00:00Z"
    And an issue "kanbus-tw-sun-fri" exists with status "closed"
    And issue "kanbus-tw-sun-fri" has closed_at at "2026-09-12T18:00:00Z"
    And issue "kanbus-tw-sun-fri" has right now summary "Friday before Sunday report."
    And an issue "kanbus-tw-sun-sat" exists with status "closed"
    And issue "kanbus-tw-sun-sat" has closed_at at "2026-09-13T12:00:00Z"
    And issue "kanbus-tw-sun-sat" has right now summary "Saturday close excluded."
    When I run "kanbus standup kanbus-tw-sun-fri kanbus-tw-sun-sat --profile meeting-script"
    Then the command should succeed
    And the standup report section "Yesterday" should mention "Friday before Sunday report"
    And the standup report section "Yesterday" should not mention "Saturday close excluded"

  Scenario: Director-brief rolling twenty-four hours includes Sunday close on Monday report
    Given standup report time is "2026-09-08T09:00:00Z"
    And an issue "kanbus-tw-db-sun" exists with status "closed"
    And issue "kanbus-tw-db-sun" has closed_at at "2026-09-07T20:00:00Z"
    And issue "kanbus-tw-db-sun" has right now summary "Sunday rolling momentum."
    When I run "kanbus standup kanbus-tw-db-sun --profile director-brief"
    Then the command should succeed
    And the standup report section "Momentum" should mention "Sunday rolling momentum"

  Scenario: Calendar mode state transition within business Yesterday qualifies for meeting-script
    Given standup report time is "2026-09-08T09:00:00Z"
    And standup window mode is calendar
    And standup skip weekends is enabled
    And an issue "kanbus-tw-cal-ev" exists with status "closed"
    And issue "kanbus-tw-cal-ev" has a state transition to "closed" at "2026-09-05T16:30:00Z"
    And issue "kanbus-tw-cal-ev" has right now summary "Friday transition yesterday."
    When I run "kanbus standup kanbus-tw-cal-ev --profile meeting-script"
    Then the command should succeed
    And the standup report section "Yesterday" should mention "Friday transition yesterday"

  Scenario: Both runtimes emit identical time window metadata for meeting-script defaults
    Given standup report time is "2026-09-08T09:00:00Z"
    And an issue "kanbus-tw-par-ms" exists with status "in_progress"
    And issue "kanbus-tw-par-ms" has right now summary "Parity calendar metadata."
    When I run "kanbus standup kanbus-tw-par-ms --profile meeting-script --json"
    Then the command should succeed
    And the standup JSON output should include fields "window_mode,lookback_hours,skip_weekends"
    And the standup JSON output should record window_mode "calendar"
    And the standup JSON output should record skip_weekends true

  Scenario: Both runtimes emit identical time window metadata for director-brief defaults
    Given standup report time is "2026-09-08T09:00:00Z"
    And an issue "kanbus-tw-par-db" exists with status "in_progress"
    And issue "kanbus-tw-par-db" has right now summary "Parity rolling metadata."
    When I run "kanbus standup kanbus-tw-par-db --profile director-brief --json"
    Then the command should succeed
    And the standup JSON output should include fields "window_mode,lookback_hours,skip_weekends"
    And the standup JSON output should record window_mode "rolling"
    And the standup JSON output should record lookback_hours 24
