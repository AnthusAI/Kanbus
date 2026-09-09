@wip
Feature: Standup time windows (rolling and calendar)
  As a Kanbus user generating standup reports
  I want lookback windows that match how teams actually run standups
  So that Yesterday and Momentum signals reflect business days, overnight work, and profile intent

  Standup signal sections evaluate issue timestamps and event `occurred_at` values against a
  resolved **time window** anchored at **report time**. Report time defaults to current UTC;
  scenarios pin it with `Given standup report time is "..."` so overnight and weekday boundaries
  are deterministic. CLI flag `--report-time` and API field `report_time` accept the same
  RFC3339 UTC value.

  Configuration (`.kanbus.yml` under `standup`):
  - `window_mode`: `rolling` | `calendar` (global default: `rolling`)
  - `lookback_hours`: positive integer; supported values in specs: `8`, `24` (global default: `24`)
  - `skip_weekends`: boolean (global default: `false`)

  CLI flags (both runtimes; names match API JSON body fields):
  - `--window-mode rolling|calendar`
  - `--lookback <duration>` where `8h`, `24h`, and `1d` are supported (`1d` resolves to `24` hours)
  - `--skip-weekends` / `--no-skip-weekends`
  - `--report-time <RFC3339 UTC>`

  Profile defaults (apply when the profile is selected and the flag or config key is unset):
  - **meeting-script**: `window_mode: calendar`, `skip_weekends: true`
  - **director-brief**: `window_mode: rolling`, `lookback_hours: 24`

  Window semantics (observable):
  - **rolling**: a timestamp qualifies when it is on or after `report_time - lookback_hours`
    and on or before `report_time` (continuous hours). `skip_weekends` is a **no-op** under
    rolling mode — weekend timestamps qualify normally.
  - **calendar** with `skip_weekends: false`: **Yesterday** spans the calendar day immediately
    before the report-time calendar date (UTC), from 00:00:00 through 23:59:59.999 on that date.
  - **calendar** with `skip_weekends: true`: **Yesterday** spans the previous **business day**
    — the most recent Monday–Friday calendar day strictly before the report-time calendar date.
  - Staleness signals (Likely questions, Risks) compare `updated_at` against `lookback_hours`
    relative to report time regardless of `window_mode`.

  JSON and API contract (CLI `--json` and console `POST /api/standup` response):
  - Top-level fields `window_mode`, `lookback_hours`, `skip_weekends`, and `report_time` record
    the resolved values used for the invocation (after profile defaults and overrides).
  - Request body field names MUST match CLI flag names (`window_mode`, `lookback_hours`,
    `skip_weekends`, `report_time`).

  Dual-runtime: scenarios in this file require identical observable behavior in Python behave
  and Rust cucumber before the `@wip` tag is removed.

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And right now litellm call tracking is reset
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-5.6-luna"

  Scenario: Global configuration defaults resolve rolling twenty-four hours without skip weekends
    Given standup report time is "2026-09-08T09:00:00Z"
    And standup window mode is rolling
    And standup lookback hours is 24
    And standup skip weekends is disabled
    And an issue "kanbus-tw-global" exists with status "in_progress"
    And issue "kanbus-tw-global" has right now summary "Global default window work."
    When I run "kanbus standup kanbus-tw-global --json"
    Then the command should succeed
    And the standup JSON output should record window_mode "rolling"
    And the standup JSON output should record lookback_hours 24
    And the standup JSON output should record skip_weekends false

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

  Scenario: Lookback duration one day resolves to twenty-four hours
    Given standup report time is "2026-09-08T09:00:00Z"
    And an issue "kanbus-tw-1d" exists with status "in_progress"
    And issue "kanbus-tw-1d" has right now summary "One day lookback work."
    When I run "kanbus standup kanbus-tw-1d --lookback 1d --json"
    Then the command should succeed
    And the standup JSON output should record lookback_hours 24

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

  Scenario: Skip weekends is a no-op under rolling window mode
    Given standup report time is "2026-09-08T09:00:00Z"
    And standup window mode is rolling
    And standup lookback hours is 24
    And standup skip weekends is enabled
    And an issue "kanbus-tw-roll-wknd" exists with status "closed"
    And issue "kanbus-tw-roll-wknd" has closed_at at "2026-09-07T20:00:00Z"
    And issue "kanbus-tw-roll-wknd" has right now summary "Sunday counts under rolling."
    When I run "kanbus standup kanbus-tw-roll-wknd --profile director-brief"
    Then the command should succeed
    And the standup report section "Momentum" should mention "Sunday counts under rolling"

  Scenario: Calendar mode without skip weekends uses previous calendar day
    Given standup report time is "2026-09-09T09:00:00Z"
    And standup window mode is calendar
    And standup skip weekends is disabled
    And an issue "kanbus-tw-cal-mon" exists with status "closed"
    And issue "kanbus-tw-cal-mon" has closed_at at "2026-09-08T16:00:00Z"
    And issue "kanbus-tw-cal-mon" has right now summary "Monday calendar yesterday."
    And an issue "kanbus-tw-cal-sun" exists with status "closed"
    And issue "kanbus-tw-cal-sun" has closed_at at "2026-09-07T16:00:00Z"
    And issue "kanbus-tw-cal-sun" has right now summary "Sunday calendar excluded."
    When I run "kanbus standup kanbus-tw-cal-mon kanbus-tw-cal-sun --profile meeting-script"
    Then the command should succeed
    And the standup report section "Yesterday" should mention "Monday calendar yesterday"
    And the standup report section "Yesterday" should not mention "Sunday calendar excluded"

  Scenario: Monday meeting-script calendar skip weekends Yesterday includes Friday excludes Saturday and Sunday
    Given standup report time is "2026-09-08T09:00:00Z"
    And an issue "kanbus-tw-mon-fri" exists with status "closed"
    And issue "kanbus-tw-mon-fri" has closed_at at "2026-09-05T17:00:00Z"
    And issue "kanbus-tw-mon-fri" has right now summary "Friday calendar yesterday."
    And an issue "kanbus-tw-mon-sat" exists with status "closed"
    And issue "kanbus-tw-mon-sat" has closed_at at "2026-09-06T12:00:00Z"
    And issue "kanbus-tw-mon-sat" has right now summary "Saturday calendar excluded."
    And an issue "kanbus-tw-mon-sun" exists with status "closed"
    And issue "kanbus-tw-mon-sun" has closed_at at "2026-09-07T15:00:00Z"
    And issue "kanbus-tw-mon-sun" has right now summary "Sunday calendar excluded."
    When I run "kanbus standup kanbus-tw-mon-fri kanbus-tw-mon-sat kanbus-tw-mon-sun --profile meeting-script"
    Then the command should succeed
    And the standup report section "Yesterday" should mention "Friday calendar yesterday"
    And the standup report section "Yesterday" should not mention "Saturday calendar excluded"
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

  Scenario: Standup help documents time window CLI flags
    When I run "kanbus standup --help"
    Then the command should succeed
    And stdout should contain "--window-mode"
    And stdout should contain "--lookback"
    And stdout should contain "--skip-weekends"
    And stdout should contain "--report-time"
    And stdout should contain "rolling"
    And stdout should contain "calendar"

  @console-server
  Scenario: Console standup API accepts and returns time window field names matching CLI JSON
    Given standup report time is "2026-09-08T09:00:00Z"
    And an issue "kanbus-tw-api" exists with status "in_progress"
    And issue "kanbus-tw-api" has right now summary "API window field parity."
    And the console server is running
    When I request a standup report from the console API with profile "meeting-script" and window_mode "calendar" and skip_weekends true
    Then the standup API response should record window_mode "calendar"
    And the standup API response should record skip_weekends true
    And the standup API response should record lookback_hours 24
    And the standup API response should record report_time "2026-09-08T09:00:00Z"

  Scenario: Both runtimes agree on time window metadata for meeting-script defaults
    Given standup report time is "2026-09-08T09:00:00Z"
    And an issue "kanbus-tw-par-ms" exists with status "in_progress"
    And issue "kanbus-tw-par-ms" has right now summary "Parity calendar metadata."
    When I run "kanbus standup kanbus-tw-par-ms --profile meeting-script --json"
    Then the command should succeed
    And the standup JSON output should include fields "window_mode,lookback_hours,skip_weekends,report_time"
    And the standup JSON output should record window_mode "calendar"
    And the standup JSON output should record skip_weekends true

  Scenario: Both runtimes agree on time window metadata for director-brief defaults
    Given standup report time is "2026-09-08T09:00:00Z"
    And an issue "kanbus-tw-par-db" exists with status "in_progress"
    And issue "kanbus-tw-par-db" has right now summary "Parity rolling metadata."
    When I run "kanbus standup kanbus-tw-par-db --profile director-brief --json"
    Then the command should succeed
    And the standup JSON output should include fields "window_mode,lookback_hours,skip_weekends,report_time"
    And the standup JSON output should record window_mode "rolling"
    And the standup JSON output should record lookback_hours 24
