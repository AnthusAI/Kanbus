# Environment variables

Every `KANBUS_*` environment variable read by the Rust (`rust/src`) and Python (`python/src`)
runtimes, with where each is read and whether the two runtimes agree. The inventory is derived from
the source, so a name that appears in either runtime appears here.

Classifications:

- **shared**: both runtimes read it with the same meaning.
- **test hook**: only honoured by the test suites. Python ignores these unless `KANBUS_ENABLE_TEST_HOOKS=1`; Rust ignores them unless built with `cfg(test)` or the `test-hooks` cargo feature (`rust/src/test_hooks.rs`). A release `kbs`/`kbsc` built with default features ignores every `KANBUS_TEST_*` variable, and the `*_for_testing` and `set_test_daemon_*` helpers in `daemon_client.rs` and `daemon_server.rs` are compiled only with the same gate. `tools/check_test_switch_gating.py` (run in CI) fails on any `KANBUS_TEST_*` read outside the gates and on any use of `PYTEST_CURRENT_TEST`.
- **single-runtime**: only one runtime has the feature, on purpose.
- **gap**: user-facing behaviour that one runtime lacks and that has not been closed.
- **legacy-cloud**: serves only the retired Cognito/IoT cloud console (its AWS stacks were deleted under kbs-14a848). The code is still present and slated for removal in a follow-up.

Settings that map to `.kanbus.yml` keys (the realtime, coordination, and overlay groups) are
described in [Configuration](CONFIGURATION.md); an environment value always wins over the YAML
value. Any variable can also live in `~/.kanbus.env` (`kbs setup env NAME --value ...`).

## Runtime variables

| Name | Purpose | Rust | Python | Class | Note |
| --- | --- | --- | --- | --- | --- |
| `KANBUS_AGENT_MODEL` | Default agent model recorded as provenance when `--agent-model` is omitted | `agent_metadata.rs:143` | `agent_metadata.py:170` | shared | See [Agent Provenance](AGENT_PROVENANCE.md) |
| `KANBUS_AGENT_NAME` | Default agent session name for provenance | `agent_metadata.rs:146` | `agent_metadata.py:172` | shared | |
| `KANBUS_AGENT_PLATFORM` | Default agent platform for provenance | `agent_metadata.rs:140` | `agent_metadata.py:168` | shared | |
| `KANBUS_AGENT_SETTINGS` | Default agent settings blob for provenance | `agent_metadata.rs:150` | `agent_metadata.py` | shared | |
| `KANBUS_COORDINATION_MUTEX_API_ENDPOINT` | Mutex API endpoint for coordination | `config_loader.rs:859` | `config_loader.py:137` | shared | Overrides `coordination.mutex_api.endpoint` |
| `KANBUS_COORDINATION_MUTEX_API_BEARER_TOKEN` | Bearer token for the mutex API | `config_loader.rs:868` | `config_loader.py:142` | shared | Credential; keep in `~/.kanbus.env` |
| `KANBUS_DAEMON` | `1`, `true`, or `yes` enables the index daemon; unset or any other value leaves it off. The CLI never spawns or waits for the daemon unless this is set | `daemon_client.rs` (`is_daemon_enabled`) | `daemon_client.py` (`is_daemon_enabled`) | shared | Daemon sockets use a 1 second connect timeout and a 30 second read/write timeout; the daemon drops a stalled connection after 10 seconds. See [Troubleshooting](TROUBLESHOOTING.md) |
| `KANBUS_FORCE_INTERACTIVE` | `1` treats the session as interactive even without a TTY | `cli.rs:1558`, `agents_management.rs` (`confirm_overwrite`) | `cli.py:338`, `agents_management.py:378` | shared | Used by the specs to feed prompts through pipes |
| `KANBUS_NON_INTERACTIVE` | `1` makes prompts fail instead of asking (currently `setup agents` overwrite) | `agents_management.rs` (`confirm_overwrite`) | `agents_management.py:374` | shared | Rust gained this in the PR that created this page |
| `KANBUS_GITHUB_API_BASE` | GitHub API base URL | `github_security_sync.rs:29` | `github_security_sync.py:42` | shared | Points sync at a test server |
| `KANBUS_SNYK_API_BASE` | Snyk API base URL | `snyk_sync.rs:33` | `snyk_sync.py:42` | shared | Points sync at a test server |
| `KANBUS_METHODOLOGY_DIRECTORY` | Exported to methodology tools with the bundle directory | `methodology_bundles.rs:32` | `methodology_bundles.py:29` | shared | Set by Kanbus, read by the tool |
| `KANBUS_NO_GUIDANCE` | Disable policy guidance output (`1`, `true`, `yes`, `on`) | `policy_guidance.rs:25` | `policy_guidance.py:35` | shared | |
| `KANBUS_NO_HOOKS` | Disable lifecycle hooks (`1`, `true`, `yes`, `on`) | `hooks.rs:131` | `hooks.py:199` | shared | See [Lifecycle Hooks](LIFECYCLE_HOOKS.md) |
| `KANBUS_OVERLAY_ENABLED` | Enable the overlay | `config_loader.rs:933` | `config_loader.py:181` | shared | Overrides `overlay.enabled` |
| `KANBUS_OVERLAY_TTL_S` | Overlay time to live in seconds | `config_loader.rs:938` | `config_loader.py:185` | shared | Overrides `overlay.ttl_s` |
| `KANBUS_REALTIME_AUTOSTART` | Start the local broker automatically (console and `gossip watch` only; the CLI never autostarts) | `config_loader.rs:887` | `config_loader.py:155` | shared | See [Realtime](REALTIME.md) |
| `KANBUS_REALTIME_BROKER` | Broker URL, `auto`, or `off`. A URL makes every CLI mutation publish to it (fire-and-forget, 2 second cap); `auto` (default) makes the CLI publish nothing and lets the console discover a broker; `off` disables realtime | `config_loader.rs:882` | `config_loader.py:151` | shared | `off` is what tests use. See [Realtime](REALTIME.md) |
| `KANBUS_REALTIME_KEEPALIVE` | MQTT keepalive seconds | `config_loader.rs:892` | `config_loader.py:159` | shared | |
| `KANBUS_REALTIME_MQTT_API_TOKEN` | Token for the MQTT API | `config_loader.rs:915` | `config_loader.py:173` | shared | Credential |
| `KANBUS_REALTIME_MQTT_CUSTOM_AUTHORIZER_NAME` | MQTT custom authorizer name | `config_loader.rs:906` | `config_loader.py:168` | shared | |
| `KANBUS_REALTIME_TOPICS_PROJECT_EVENTS` | Project events topic | `config_loader.rs:924` | `config_loader.py:177` | shared | |
| `KANBUS_REALTIME_TRANSPORT` | Realtime transport selector | `config_loader.rs:877` | `config_loader.py:147` | shared | |
| `KANBUS_REALTIME_UDS_SOCKET_PATH` | Unix socket path for the local transport | `config_loader.rs:897` | `config_loader.py:163` | shared | |
| `KANBUS_REALTIME_WARN_MOSQUITTO` | Control the warning when no Mosquitto broker is reachable | `gossip.rs:1913` | `gossip.py:1105` | shared | |
| `KANBUS_STANDUP_REPORT_TIME` | Default stand-up report time of day | `standup_window.rs:17` | `standup_window.py:19` | shared | |
| `KANBUS_USER` | Override the acting user name (blank is ignored) | `users.rs:7` | `users.py:14` | shared | Falls back to `USER` |
| `KANBUS_SNYK_DEBUG` | `1` prints debug lines during Snyk sync | `snyk_sync.rs:100` | none | gap | Debug output only; not ported, see Gaps |
| `KANBUS_ROUTER_MQTT_DIAGNOSTICS` | `1` prints MQTT transport diagnostics when the router listener fails to connect | none | `coordination_runtime.py:68` | gap | Consumed only by `tools/issue_router_integration_harness.py`; not ported, see Gaps |

## Legacy-cloud variables

All read by Rust only. They configure the retired Cognito/IoT cloud console (`console_lambda`
binary and `kbs cloud token` commands). Remove together with that code.

| Name | Purpose | Rust | Python | Class |
| --- | --- | --- | --- | --- |
| `KANBUS_API_STAGE` | API Gateway stage prefix stripped from request paths | `bin/console_lambda.rs:127` | none | legacy-cloud |
| `KANBUS_AUTH_MODE` | `none` or Cognito PKCE | `bin/console_lambda.rs:170`, `:225` | none | legacy-cloud |
| `KANBUS_CLOUD_API_BASE_URL` | Base URL for `kbs cloud token` | `cli.rs:4838` | none | legacy-cloud |
| `KANBUS_CLOUD_ID_TOKEN` | Admin ID token for `kbs cloud token` | `cli.rs:4856` | none | legacy-cloud |
| `KANBUS_COGNITO_CLIENT_ID` | Cognito app client | `bin/console_lambda.rs:189` | none | legacy-cloud |
| `KANBUS_COGNITO_DOMAIN_URL` | Cognito hosted UI domain | `bin/console_lambda.rs:188` | none | legacy-cloud |
| `KANBUS_COGNITO_ISSUER` | Token issuer | `bin/console_lambda.rs:192` | none | legacy-cloud |
| `KANBUS_COGNITO_LOGOUT_URI` | Logout redirect | `bin/console_lambda.rs:191` | none | legacy-cloud |
| `KANBUS_COGNITO_REDIRECT_URI` | Login redirect | `bin/console_lambda.rs:190` | none | legacy-cloud |
| `KANBUS_IDENTITY_POOL_ID` | Cognito identity pool | `bin/console_lambda.rs:193` | none | legacy-cloud |
| `KANBUS_IOT_DATA_ENDPOINT` | AWS IoT data endpoint for realtime presigning | `bin/console_lambda.rs:330` | none | legacy-cloud |
| `KANBUS_MQTT_CUSTOM_AUTHORIZER_NAME` | IoT custom authorizer name | `bin/console_lambda.rs:345` | none | legacy-cloud |
| `KANBUS_TENANT_ACCOUNT_CLAIM_KEY` | Token claim holding the account (default `custom:account`) | `bin/console_lambda.rs:202` | none | legacy-cloud |
| `KANBUS_TENANT_PROJECT_CLAIM_KEY` | Token claim holding the project (default `custom:project`) | `bin/console_lambda.rs:207` | none | legacy-cloud |

## Console server variables

Read by the Rust `kbsc` console server only; the Python package has no console. These do not use the
`KANBUS_` prefix.

| Name | Purpose | Rust | Python | Class | Note |
| --- | --- | --- | --- | --- | --- |
| `CONSOLE_HOST` | Interface `kbsc` listens on. Unset or empty means every interface (`0.0.0.0`), so other devices on the local network can open the board. `localhost` means `127.0.0.1`. Any other value must be an IP address; an invalid value stops `kbsc` at startup with exit status 1 and an error naming the value. | `bin/console_local.rs` (`resolve_bind_host`) | none | single-runtime | Reads are unauthenticated on the network; writes (comments, status changes, assignments) are accepted from localhost only. Set `CONSOLE_HOST=127.0.0.1` to listen on loopback only. See [Open the console](getting-started/local-files.md#7-open-the-console) |
| `CONSOLE_PORT` | Port `kbsc` listens on; overrides `console_port` in `.kanbus.yml` (default 5174 when neither is set) | `bin/console_local.rs` | none | single-runtime | Give each repository its own port |

## Test hooks

Not for users. Both runtimes gate them (see the classification notes above).

| Name | Rust | Python | Class |
| --- | --- | --- | --- |
| `KANBUS_ENABLE_TEST_HOOKS` (gate) | none (compile-time `test-hooks` feature) | `test_hooks.py:6` | single-runtime |
| `KANBUS_TEST_AI_MOCK` | `summarize.rs:284` | `ai_summarize.py:71` | test hook, shared |
| `KANBUS_TEST_AI_REQUIRE_ENV_CREDENTIALS` | `right_now.rs:941` | `right_now.py:791` | test hook, shared |
| `KANBUS_TEST_DISABLE_SERVICE` | none | `issue_files.py:77` | test hook, Python-only |
| `KANBUS_TEST_CANONICALIZE_FAILURE` | `file_io.rs:63` | `project.py:264` | test hook, shared |
| `KANBUS_TEST_CONFIGURATION_PATH_FAILURE` | `file_io.rs:488` | `project.py:353` | test hook, shared |
| `KANBUS_TEST_LITELLM_COMPLETION` | `litellm_completion.rs:14` | `right_now.py:867` | test hook, shared |
| `KANBUS_RIGHT_NOW_LITELLM_CALLED` (marker written by the hook) | `litellm_completion.rs:13` | `right_now.py:869` | test hook, shared |
| `KANBUS_TEST_MOSQUITTO_UNAVAILABLE` | `gossip.rs:1667` | `gossip.py:730` | test hook, shared |
| `KANBUS_TEST_RIGHT_NOW_COMPLETION` | `right_now.rs:59` | `right_now.py:43` | test hook, shared |
| `KANBUS_TEST_SIMULATE_LITELLM_MISSING` | `right_now.rs:347` | `right_now.py:877` | test hook, shared |
| `KANBUS_TEST_STANDUP_ROLLUP_COMPLETION` | `standup_rollup_reduce.rs:14` | `standup_rollup_reduce.py:27` | test hook, shared |
| `KANBUS_TEST_SCREENSHOT_CAPTURE_OPTIONS` | `console_screenshot.rs:15` | `console_screenshot.py:23` | test hook, shared |
| `KANBUS_TEST_SCREENSHOT_FORCE_NODE_MISSING` | `console_screenshot.rs:19` | `console_screenshot.py:27` | test hook, shared |
| `KANBUS_TEST_SCREENSHOT_HIDE_PACKAGE_SCRIPT` | `console_screenshot.rs:18` | `console_screenshot.py:26` | test hook, shared |
| `KANBUS_TEST_SCREENSHOT_LAST_MODE` | `console_screenshot.rs:14` | `console_screenshot.py:22` | test hook, shared |
| `KANBUS_TEST_SCREENSHOT_MOCK` | `console_screenshot.rs:165` | `console_screenshot.py:179` | test hook, shared |
| `KANBUS_TEST_SCREENSHOT_NODE_EXECUTABLE` | `console_screenshot.rs:20` | `console_screenshot.py:28` | test hook, shared |
| `KANBUS_TEST_SCREENSHOT_PREREQUISITES_VERIFIED` | `console_screenshot.rs:16` | `console_screenshot.py:24` | test hook, shared |
| `KANBUS_TEST_SCREENSHOT_SCRIPT_SEARCH_ROOT` | `console_screenshot.rs:17` | `console_screenshot.py:25` | test hook, shared |
| `KANBUS_TEST_COORDINATION_NOW` | `coordination.rs:145` | none | single-runtime |
| `KANBUS_TEST_DOTENV_APPLIED_ONCE` | `config_loader.rs:989` | none | single-runtime |
| `KANBUS_TEST_EXTERNAL_TIMEOUT_MS` | `content_validation.rs:203` | none | single-runtime |
| `KANBUS_TEST_EXTERNAL_TOOL_MISSING` | `content_validation.rs:132` | none | single-runtime |
| `KANBUS_TEST_HOOKS_SELF_CHECK` | `test_hooks.rs:28` | none | single-runtime |
| `KANBUS_TEST_INVALID_STATUS` | `workflows.rs:205` | none | single-runtime |
| `KANBUS_TEST_LOCAL_LISTING_ERROR` | `issue_listing.rs:299` | none | single-runtime |
| `KANBUS_TEST_RESOLVE_VAR` | `ai_credentials.rs:455` | none | single-runtime |
| `KANBUS_TEST_SCREENSHOT_ASSUME_SERVER` | `console_screenshot.rs:151` | none | single-runtime |

## Prefixes and non-variables

These strings match `KANBUS_*` in the source but are not variables with a single value.

| String | Where | Meaning |
| --- | --- | --- |
| `KANBUS_REALTIME_`, `KANBUS_COORDINATION_` | `gossip.rs:2005`, `cli.rs:5297` (Rust unit tests) | Prefixes stripped from the process environment so a developer's `~/.kanbus.env` cannot leak into tests |
| `KANBUS_AGENT_` | docs only | Shorthand for the four `KANBUS_AGENT_*` variables |
| `KANBUS_SECTION_HEADER`, `KANBUS_SECTION_LINES` | `agents_management.rs:22`, `agents_management.py:30` | Constants holding the AGENTS.md template text |
| `KANBUS_SECTION_TEXT` | `agents_management.py:43` | Python constant for the same template |
| `KANBUS_VERSION_MESSAGE` | `kanbus_version.rs:9`, `kanbus_version.py:11` | Suffix of the constant `INVALID_KANBUS_VERSION_MESSAGE` |

No `KANBUS_*` name is built dynamically at runtime in either runtime. The `.kanbus.yml` flattening
described under "Loading semantics" in [Configuration](CONFIGURATION.md) uses fixed names listed above.

## Other components

Variables used outside the two CLI runtimes. They are listed so nothing in the repository is
undocumented; they do not need Rust/Python parity.

| Component | Variables |
| --- | --- |
| Hosted API (`services/kanbus-api`, `packages/cdk`, `packages/api-client`) | `KANBUS_BACKEND`, `KANBUS_OBJECT_BUCKET`, `KANBUS_CATALOG_TABLE`, `KANBUS_SERVICE_PRINCIPALS`, `KANBUS_ARCHIVE_RETENTION_DAYS`, `KANBUS_REQUIRED_GROUP`, `KANBUS_NAMESPACE`, `KANBUS_ROOT`, `KANBUS_TENANT`, `KANBUS_PROJECT`, `KANBUS_PORT`, `KANBUS_LOCAL_TOKEN`, `KANBUS_API_URL`, `KANBUS_SERVICE_API_URL`, `KANBUS_API_LOCAL_BINARY`, `KANBUS_API_LOCAL_CONFIGURATION` |
| Console app and UI package | `KANBUS_PYTHON`, `KANBUS_PYTHONPATH`, `KANBUS_PYTHON_ARGS`, `KANBUS_THEME`, `KANBUS_THEMES`, `KANBUS_THEME_FONTS`, `KANBUS_UI_SCREENSHOT_DIRECTORY`, `KANBUS_REFRESH_SNAPSHOT__`, `KANBUS_TEST_STANDUP_FAIL`, `KANBUS_TEST_WIKI_RATE_LIMIT_MAX` |
| Integration harnesses (`tools/`) | `KANBUS_RUN_LIVE_COORDINATION_HARNESS`, `KANBUS_RUN_LIVE_ROUTER_HARNESS`, `KANBUS_RUN_LIVE_ROUTER_CONTAINER_HARNESS`, `KANBUS_HARNESS_*` (board CLI, fake adapter, MQTT, mutex API, tenant, workers), `KANBUS_LIVE_BEDROCK`, `KANBUS_PARITY_STRICT`, `KANBUS_SOURCE_PATTERN` (a Python constant) |
| Test runners and CI | `KANBUS_CUCUMBER_FEATURE_FILTER`, `KANBUS_CUCUMBER_INCLUDE_CONSOLE`, `KANBUS_CUCUMBER_ONLY_CONSOLE`, `KANBUS_ENABLE_COVERAGE_HELPER`, `KANBUS_RUST_BINARY` |
| Scripts and fixtures | `KANBUS_DEMO_KEEP`, `KANBUS_COMPACTION_HOOK_TIMEOUT_SECONDS`, `KANBUS_PROJECT_KEY` (written to `.env` by configuration specs), `KANBUS_GITHUB_TOKEN` (a name used by router specs, not read by the runtimes), `KANBUS_OFFERS` (marketing site) |

## Gaps

- **`KANBUS_NON_INTERACTIVE` and `KANBUS_FORCE_INTERACTIVE`** (closed): Rust ignored `KANBUS_NON_INTERACTIVE` and prompted on a piped stdin. Scenarios in `features/agents/agents_management.feature` now cover non-interactive mode ignoring a piped confirmation, piped stdin without forced interactivity refusing to prompt, and forced interactivity accepting a piped confirmation. The first two failed in Rust before the fix. `kbs setup agents` now refuses to prompt, with Python's exact message and exit code, when `KANBUS_NON_INTERACTIVE=1` or when stdin is not a terminal and `KANBUS_FORCE_INTERACTIVE` is not `1`. The Rust steps spawn `kbs` with a piped stdin (never a TTY) and add or remove `KANBUS_FORCE_INTERACTIVE`, the same mechanism the Python steps use through `CliRunner`.
- **`KANBUS_SNYK_DEBUG`** (not ported): Rust prints developer debug lines while syncing Snyk (the sample project line depends on `HashMap` iteration order and the format uses Rust `Debug` quoting), and Python has a Snyk sync without them. No spec covers Snyk output and exercising it needs a fake Snyk server in both runtimes, so it stays listed as a gap.
- **`KANBUS_ROUTER_MQTT_DIAGNOSTICS`** (not ported): Python emits a JSON snapshot of its MQTT transport state when the router listener cannot connect. It is harness diagnostics, consumed only by `tools/issue_router_integration_harness.py`. The Rust router has MQTT coordination but no transport-diagnostics model, so porting needs new Rust state plus harness changes.
