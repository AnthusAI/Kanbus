Feature: Standup time windows (rolling vs calendar)
  As a Kanbus user generating standup reports
  I want explicit window / lookback / skip_weekends controls
  So that completed vs active buckets match overnight bots and spoken calendar standups

  Nomenclature (locked — do not invent synonyms):
  - window: rolling | calendar
  - lookback: duration for rolling (hours required; days are sugar, e.g. 1d = 24h)
  - skip_weekends: boolean; meaningful for calendar only; no-op when window is rolling

  Defaults (locked):
  - Global config: window rolling, lookback 24h, skip_weekends false
  - meeting-script profile override: window calendar, skip_weekends true
  - director-brief profile: inherit global rolling + 24h
  - CLI/API/config use the same field names: window, lookback, skip_weekends
  - CLI overrides: --window, --lookback, --skip-weekends / --no-skip-weekends

  Rolling behavior:
  - Completed bucket ("Yesterday" in meeting-script): closed/done within lookback before report time
  - Active bucket ("Today"): in_progress or blocked at report time
  - skip_weekends is ignored (no effect) when window is rolling
  - Hour granularity is required (e.g. 8h overnight); not days-only

  Timezone (locked):
  - Canonical source: standup.timezone in project configuration
  - When standup.timezone is unset, use the system local timezone (no other fallback)

  Calendar behavior:
  - Buckets align to calendar days in the resolved standup timezone
  - skip_weekends false: completed bucket is the previous calendar day only
  - skip_weekends true: Monday completed bucket includes Friday + Saturday + Sunday;
    Tuesday–Friday completed bucket is the previous calendar day only
  - Weeks are YAGNI — no week mode

  Background:
    Given a Kanbus project with default configuration
    And mock AI is enabled
    And the Kanbus configuration uses AI provider "litellm" with model "gpt-5.6-luna"

  Scenario: Global defaults are rolling lookback 24h without skip_weekends
    When I inspect standup window configuration
    Then standup window should be "rolling"
    And standup lookback should be "24h"
    And standup skip_weekends should be false

  Scenario: meeting-script profile defaults to calendar with skip_weekends
    When I resolve standup window settings for profile "meeting-script"
    Then standup window should be "calendar"
    And standup skip_weekends should be true

  Scenario: director-brief profile defaults to rolling 24h
    When I resolve standup window settings for profile "director-brief"
    Then standup window should be "rolling"
    And standup lookback should be "24h"
    And standup skip_weekends should be false

  Scenario: Rolling lookback 8h overnight includes recent closures and excludes older ones
    Given standup window is "rolling"
    And standup lookback is "8h"
    And the report time is fixed
    And an issue "kanbus-win-8h-in" exists with status "closed"
    And issue "kanbus-win-8h-in" has closed_at 3 hours before report time
    And issue "kanbus-win-8h-in" has right now summary "Shipped overnight hotfix."
    And an issue "kanbus-win-8h-out" exists with status "closed"
    And issue "kanbus-win-8h-out" has closed_at 12 hours before report time
    And issue "kanbus-win-8h-out" has right now summary "Yesterday afternoon cleanup."
    And an issue "kanbus-win-8h-wip" exists with status "in_progress"
    And issue "kanbus-win-8h-wip" has right now summary "Morning WIP."
    When I run "kanbus standup --window rolling --lookback 8h --profile meeting-script kanbus-win-8h-in kanbus-win-8h-out kanbus-win-8h-wip"
    Then the command should succeed
    And the standup report section "Yesterday" should mention "Shipped overnight hotfix"
    And the standup report section "Yesterday" should not mention "Yesterday afternoon cleanup"
    And the standup report section "Today" should mention "Morning WIP"

  Scenario: Lookback 1d is sugar for 24h on rolling window
    Given standup window is "rolling"
    And standup lookback is "1d"
    When I resolve standup lookback duration
    Then standup lookback hours should be 24

  Scenario: skip_weekends is a no-op when window is rolling
    Given standup window is "rolling"
    And standup lookback is "24h"
    And standup skip_weekends is true
    And an issue "kanbus-win-roll-skip" exists with status "closed"
    And issue "kanbus-win-roll-skip" has closed_at within standup lookback
    And issue "kanbus-win-roll-skip" has right now summary "Rolling ignore weekends."
    When I run "kanbus standup --window rolling --lookback 24h --skip-weekends --profile meeting-script kanbus-win-roll-skip"
    Then the command should succeed
    And the standup report section "Yesterday" should mention "Rolling ignore weekends"

  Scenario: Calendar without skip_weekends uses previous calendar day only
    Given standup window is "calendar"
    And standup skip_weekends is false
    And standup timezone is "America/New_York"
    And the report time is Tuesday 10:00 in standup timezone
    And an issue "kanbus-win-cal-mon" exists with status "closed"
    And issue "kanbus-win-cal-mon" closed on the previous calendar day in standup timezone
    And issue "kanbus-win-cal-mon" has right now summary "Monday close."
    And an issue "kanbus-win-cal-old" exists with status "closed"
    And issue "kanbus-win-cal-old" closed two calendar days before report day in standup timezone
    And issue "kanbus-win-cal-old" has right now summary "Sunday close."
    When I run "kanbus standup --window calendar --no-skip-weekends --profile meeting-script kanbus-win-cal-mon kanbus-win-cal-old"
    Then the standup report section "Yesterday" should mention "Monday close"
    And the standup report section "Yesterday" should not mention "Sunday close"

  Scenario: Calendar skip_weekends on Monday bundles Friday Saturday Sunday
    Given standup window is "calendar"
    And standup skip_weekends is true
    And standup timezone is "America/New_York"
    And the report time is Monday 10:00 in standup timezone
    And an issue "kanbus-win-fri" exists with status "closed"
    And issue "kanbus-win-fri" closed on Friday before this Monday in standup timezone
    And issue "kanbus-win-fri" has right now summary "Friday ship."
    And an issue "kanbus-win-sat" exists with status "closed"
    And issue "kanbus-win-sat" closed on Saturday before this Monday in standup timezone
    And issue "kanbus-win-sat" has right now summary "Saturday fix."
    And an issue "kanbus-win-sun" exists with status "closed"
    And issue "kanbus-win-sun" closed on Sunday before this Monday in standup timezone
    And issue "kanbus-win-sun" has right now summary "Sunday tweak."
    And an issue "kanbus-win-thu" exists with status "closed"
    And issue "kanbus-win-thu" closed on Thursday before this Monday in standup timezone
    And issue "kanbus-win-thu" has right now summary "Thursday leftover."
    When I run "kanbus standup --window calendar --skip-weekends --profile meeting-script kanbus-win-fri kanbus-win-sat kanbus-win-sun kanbus-win-thu"
    Then the standup report section "Yesterday" should mention "Friday ship"
    And the standup report section "Yesterday" should mention "Saturday fix"
    And the standup report section "Yesterday" should mention "Sunday tweak"
    And the standup report section "Yesterday" should not mention "Thursday leftover"

  Scenario: CLI help documents window lookback skip_weekends flags
    When I run "kanbus standup --help"
    Then the command should succeed
    And command help should mention "--window"
    And command help should mention "--lookback"
    And command help should mention "--skip-weekends"

  Scenario: CLI flags override config and profile on standup run
    Given the Kanbus configuration sets standup window to "calendar"
    And the Kanbus configuration sets standup lookback to "24h"
    And the Kanbus configuration sets standup skip_weekends to true
    And the report time is fixed
    And an issue "kanbus-cli-ov-in" exists with status "closed"
    And issue "kanbus-cli-ov-in" has closed_at 3 hours before report time
    And issue "kanbus-cli-ov-in" has right now summary "CLI rolling include."
    And an issue "kanbus-cli-ov-out" exists with status "closed"
    And issue "kanbus-cli-ov-out" has closed_at 12 hours before report time
    And issue "kanbus-cli-ov-out" has right now summary "CLI rolling exclude."
    When I run "kanbus standup --window rolling --lookback 8h --no-skip-weekends --profile meeting-script kanbus-cli-ov-in kanbus-cli-ov-out"
    Then the command should succeed
    And the standup report section "Yesterday" should mention "CLI rolling include"
    And the standup report section "Yesterday" should not mention "CLI rolling exclude"

  @console-server
  Scenario: Console API accepts the same window lookback skip_weekends field names
    Given the console server is running
    When I POST "/api/standup" with JSON:
      """
      {
        "profile": "meeting-script",
        "window": "rolling",
        "lookback": "8h",
        "skip_weekends": false
      }
      """
    Then the response should accept fields "window", "lookback", and "skip_weekends"

  @python-parity
  Scenario: Dual-runtime parity for window settings resolution
    Given standup window is "rolling"
    And standup lookback is "8h"
    When I resolve standup window settings in both runtimes
    Then Python and Rust should agree on window "rolling"
    And Python and Rust should agree on lookback hours 8
