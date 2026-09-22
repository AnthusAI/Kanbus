# Issue Router integration harness

## Board-backed Docker race (opt-in)

`tools/issue_router_container_integration_harness.py` is the repeatable live
integration test for dispatching a real Kanbus board task from separate Python
and Rust worker containers. It builds the pinned Codex worker image, creates a
disposable routed task under the fixed `Issue Router Testing` epic
(`kbs-d3973c07-13a1-4598-8f32-85e010278121`), races both runtimes against one
isolated Git mirror, and verifies that exactly one worker starts the task and
publishes its result comment. The task asks for exactly three short paragraphs
of Lorem ipsum text and explicitly forbids source changes. If the fixed epic is
absent, the harness creates it; if that ID belongs to anything else, it stops
without replacing it.
Each task gets a unique agent-class label that only the two worker clones are
configured to handle; they have no other routed classes, so older open tasks in
the test epic cannot win scheduling. This keeps any already-running production
router from claiming the test task. The worker-only config also disables the
forge adapter, so the test cannot push a feature branch or open a GitHub pull
request. Codex's nested sandbox is bypassed only inside these disposable Docker
workers because the container runtime cannot create its own nested namespaces;
the workers can access only their temporary checkout and mirror, not the host
repository or host filesystem.

This test makes real board changes: it temporarily pushes the generated test
task, then imports the router result and leaves the successful task in the
configured Review stage so the result remains visible on the board. If a run
fails, it preserves the generated issue and diagnostic fixture for inspection
instead of closing the issue or erasing its history. Router-state stays inside
the disposable Git mirror and is not pushed to production. Both `--live`
and `--publish-board` are required, as is the
environment opt-in `KANBUS_RUN_LIVE_ROUTER_CONTAINER_HARNESS=1`. Set the
production/test MQTT, mutex API, and OpenAI credentials in the environment; the
harness passes only its explicit credential allowlist into worker containers
and maps `OPENAI_API_KEY` to Codex CLI's `CODEX_API_KEY` variable. It does not
write secrets to `.kanbus.yml` or the repository. Run only from a
clean checkout matching `origin/develop`:

~~~bash
KANBUS_RUN_LIVE_ROUTER_CONTAINER_HARNESS=1 \
KANBUS_COORDINATION_MUTEX_API_ENDPOINT=https://… \
KANBUS_COORDINATION_MUTEX_API_BEARER_TOKEN=… \
KANBUS_REALTIME_BROKER=mqtts://… \
KANBUS_REALTIME_MQTT_CUSTOM_AUTHORIZER_NAME=… \
KANBUS_REALTIME_MQTT_API_TOKEN=… \
OPENAI_API_KEY=… \
conda run -n py311 python tools/issue_router_container_integration_harness.py --live --publish-board
~~~

Use credentials dedicated to integration testing; this test publishes a
disposable task and coordination events. Add `--keep` to retain its temporary
controller, mirror, and worker checkouts for diagnosis. It requires a running
Docker daemon, working board CLI authentication, and permission to push to
`develop`. A Docker CLI without an available daemon is not sufficient.

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
