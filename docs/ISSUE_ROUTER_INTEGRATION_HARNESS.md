# Issue Router integration harness

The tool at tools/issue_router_integration_harness.py exercises the Python and
Rust Kanbus router plan and router run --once commands in two isolated worker
clones of a disposable Kanbus project. Its bare Git remote and independent
observer clone are created under a temporary directory; the current Kanbus
board is never used. By default, coordination is Git-only and no external
service is contacted.

Run the focused offline harness from the repository root:

~~~bash
conda run -n py311 python tools/issue_router_integration_harness.py --python-worker 'conda run -n py311 python -m kanbus.cli' --rust-worker '/path/to/kbs'
~~~

The Python and Rust command options are prefixes. They are split as argument
vectors and are never invoked through a shell. The default Python worker uses
the current interpreter. The default Rust worker is kbs.

The harness generates a temporary fake Codex executable. It logs adapter
starts and emits the version 1 six-field result object used by the router
contract:

~~~json
{
  "schema_version": 1,
  "outcome": "completed",
  "summary": "Disposable Issue Router integration result.",
  "issue_updates": [],
  "checkpoint": null,
  "artifacts": []
}
~~~

The offline checks compare Python and Rust plan output byte-for-byte, then
exercise `router run --once` using Git-only coordination. While the Python
worker holds the primary package, the Rust worker fetches
`refs/heads/kanbus/router-state`. Its plan must exclude the primary package and
contain only the secondary package; the Rust worker then executes that
secondary package. An independent observer verifies the shared `in_progress`
status and active claim before the second run, then fetches runtime-published
state and verifies both `review` statuses, released claims, durable
claim/result events, and output refs. The harness does not commit or push board
state on behalf of either router after a run; helper pushes are limited to
fixture setup before router execution.

This connected-clone scenario does not simulate a Git network partition and
does not claim to demonstrate duplicate starts. The focused stale-publication
tests validate the harness's rejection checks, but do not exercise a real
partitioned runtime race. Runtime-level tests must cover stale claim/revision
fencing separately until a partition simulation can isolate the clones before
either observes the other's start.

## Optional live coordination

Live services are ignored unless the --live option is passed and the explicit
gate is set:

~~~bash
export KANBUS_RUN_LIVE_ROUTER_HARNESS=1
~~~

To add the hard Mutex API race, set both values below. The harness creates a
separate disposable fixture, configures it before router execution, runs the
same package concurrently in two clones, and requires exactly one fake adapter
start. The losing clone must fetch and observe the winner's runtime-published
review state without a helper commit or push:

~~~bash
export KANBUS_HARNESS_MUTEX_API_ENDPOINT='https://<mutex-api-host>'
export KANBUS_HARNESS_MUTEX_API_TOKEN='<bearer-token>'
~~~

MQTT configuration is optional. If a broker is set, all five MQTT values are
required and passed to the worker processes through their environment:

~~~bash
export KANBUS_HARNESS_MQTT_BROKER='mqtts://<broker-host>:8883'
export KANBUS_HARNESS_MQTT_CUSTOM_AUTHORIZER='<authorizer-name>'
export KANBUS_HARNESS_MQTT_API_TOKEN='<mqtt-token>'
export KANBUS_HARNESS_TENANT_ACCOUNT='<account>'
export KANBUS_HARNESS_TENANT_PROJECT='<project>'
~~~

When all five MQTT values are present, the same `--live` run adds a separate
Python-versus-Rust soft-coordination race. It seeds one routed package into a
disposable bare Git remote, configures provider order `[mqtt, git]`, and starts
both workers concurrently. Each worker must observe both MQTT claim IDs; the
shared router-state branch must contain exactly one accepted start, and exactly
one fake adapter may run. The fixture uses a five-second contention window and
a 30-second lease. MQTT claims use QoS 0 with the retain flag disabled, matching
the runtime transport. The harness does not deploy AWS resources or provision
credentials; it uses only the broker and authorizer values already in the
environment.

Run with a bounded lease and command timeout:

~~~bash
conda run -n py311 python tools/issue_router_integration_harness.py --live --ttl-seconds 15 --timeout-seconds 60 --python-worker 'conda run -n py311 python -m kanbus.cli' --rust-worker '/path/to/kbs'
~~~

Secret-like environment values are redacted from captured child output. Child
process groups receive bounded termination on timeout, and temporary fixtures
are removed on success or failure unless --keep is supplied. The --keep option
preserves only the disposable fixture for inspection.

The live MQTT and Mutex races run in isolated local clones against local bare
Git remotes while connecting to the configured external services. They verify
broker-visible coordination across runtimes, but do not model a Git network
partition or replace a later test with the router processes on separate
machines.

This harness does not invoke GitHub, create pull requests, or launch real
coding agents. The generated fake adapter validates the CLI execution,
structured-result, coordination, and publication path only.
