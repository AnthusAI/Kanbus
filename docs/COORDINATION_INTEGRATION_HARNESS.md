# Live coordination integration harness

`tools/coordination_integration_harness.py` is an opt-in integration check for
the Kanbus CLI dispatcher and coordination providers. It creates a disposable
task through the normal CLI, creates a temporary bare Git remote and two
independent clones, and races one Python CLI process with one Rust CLI process.
Before the hard race, it starts a Python MQTT watcher and sends a coordination
claim from the Rust worker with the provider list `[mqtt, git]`; it requires the
watcher to print a valid matching `coordination.claim` envelope.
The hard claim winner advances the fixture task to `in_progress`; the loser
must report a held lease. The harness then checks inspect, expiry, takeover,
release, and duplicate soft claims with the mutex provider disabled.

This validates the dispatcher fixture and coordinator behavior. It does not
validate or represent a production router, which does not exist yet.

The harness does not run as part of the normal test suite. It will not create
network state unless `KANBUS_RUN_LIVE_COORDINATION_HARNESS=1` is set and all
required service and worker inputs are present. It uses only the supplied
Mutex API and MQTT endpoints; it does not deploy AWS resources. The generated
Git remote, clones, task, and event data are removed at the end unless `--keep`
is supplied. A best-effort API release is attempted for this run's unique hard
resource on failure or interruption.

## Same-host emulation

Build the Rust CLI with coordination commands and make the Python CLI available
in the `py311` environment. The Python package must resolve to the checkout
being tested (for example, installed editable). Set these inputs in the shell;
keep the two tokens in your shell's secret store or enter them without echoing.

```sh
export KANBUS_RUN_LIVE_COORDINATION_HARNESS=1
export KANBUS_HARNESS_MUTEX_API_ENDPOINT='https://<mutex-api-host>'
read -s KANBUS_HARNESS_MUTEX_API_TOKEN
export KANBUS_HARNESS_MUTEX_API_TOKEN
export KANBUS_HARNESS_MQTT_BROKER='mqtts://<iot-endpoint>:8883'
export KANBUS_HARNESS_MQTT_CUSTOM_AUTHORIZER='<custom-authorizer-name>'
read -s KANBUS_HARNESS_MQTT_API_TOKEN
export KANBUS_HARNESS_MQTT_API_TOKEN
export KANBUS_HARNESS_TENANT_ACCOUNT='<the MQTT token account scope>'
export KANBUS_HARNESS_TENANT_PROJECT='<the MQTT token project scope>'
export KANBUS_HARNESS_PYTHON_WORKER='conda run -n py311 python -m kanbus.cli'
export KANBUS_HARNESS_RUST_WORKER='/absolute/path/to/Kanbus/rust/target/release/kbs'

conda run -n py311 python tools/coordination_integration_harness.py
```

The MQTT broker input must be a full `mqtt://` or `mqtts://` URL. The tenant
account and project must exactly match the MQTT API token scope; they are each
one safe MQTT topic segment. The script configures both workers for
`projects/<account>/<project>/events`, disables broker autostart and keepalive,
and assigns a different UDS path to each clone. The initial project config uses
the ordered providers `[mutex_api, mqtt, git]`; credentials are passed to child
processes through environment variables and are not written to the fixture config.
`--ttl-seconds` accepts 1 through 30 seconds and defaults to 5. Use `--keep` to
retain the temporary project for inspection.

The same-host delivery probe sends from the Rust clone to a watcher running in
the Python clone. It restores `[mutex_api, mqtt, git]` before starting the hard
acquire race.

## Two actual machines

The automated harness is same-host because it owns the temporary bare remote
and launches both subprocesses. For a real two-machine run, use a disposable
fixture repository on a shared Git service, with a separate clone and checkout
on each machine. Do not share a working directory or UDS socket. Configure both
checkouts with the same project key, tenant-scoped topic
`projects/<account>/<project>/events`, and coordination TTL, and set each
machine's MQTT broker, custom authorizer, MQTT API token, Mutex API endpoint,
and bearer token in its own environment. Keep the `.kanbus.yml` provider order
as `[mutex_api, mqtt, git]` and set a short test TTL such as `5s`.

On one machine, create a uniquely titled disposable task using `kbs create`
and push the issue through the normal Kanbus workflow. Pull that commit on the
other machine. Set the full task ID on both machines and choose one shared,
unique run ID, then use a namespaced resource to avoid colliding with other
leases:

```sh
TASK_ID='<full-task-id>'
RUN_ID='<unique-run-id>'
RESOURCE="harness:${RUN_ID}:issue:${TASK_ID}"
MQTT_PROBE_RESOURCE="harness:${RUN_ID}:mqtt-delivery-probe"
```

First, temporarily set both provider lists to `[mqtt, git]`. Run an MQTT
watcher on one machine and publish a claim from the other, using the Python CLI
on one side and the Rust binary on the other:

```sh
# Receiver machine
conda run -n py311 python -m kanbus.cli gossip watch --transport mqtt --broker "$KANBUS_REALTIME_BROKER" --no-autostart --print

# Sender machine
kbs coordination claim --resource "$MQTT_PROBE_RESOURCE" --owner worker-b --claim-id mqtt-probe-claim --revision 1
```

The receiver should print a JSON envelope whose `type` is
`coordination.claim` and whose resource, owner, and claim ID match the sender.
Stop the watcher, restore `[mutex_api, mqtt, git]` on both machines, and run the
hard-lease checks below with `RESOURCE`:

```sh
kbs coordination claim --resource "$RESOURCE" --owner worker-a --claim-id claim-a --revision 1
kbs coordination claim --resource "$RESOURCE" --owner worker-b --claim-id claim-b --revision 1
```

Exactly one command should report `provider: mutex_api` and `state: active hard
mutex`; the other should fail with a held-lease message. The winner can then
advance the disposable task with `kbs update "$TASK_ID" --status in_progress`
and push that issue update. Run `kbs coordination inspect --resource "$RESOURCE"`
from either machine and confirm the owner. Wait for the displayed expiry, then
claim again from the other machine with `--revision 2`, inspect the takeover,
and release it with `kbs coordination release` using the takeover owner and
claim ID. Inspect should then report `eligible`.

To demonstrate soft duplicate behavior, remove `mutex_api` from both provider
lists (for example, use `[mqtt, git]`) and use a new resource key for the same
disposable task. Run the two claims simultaneously. Both may succeed because
soft coordination records competing claims without a hard acquire. Restore the
normal project config afterward and close or delete the disposable task using
the standard Kanbus CLI.

This manual two-machine procedure exercises the coordination CLI and fixture
task only. It does not establish that a production routing workflow is wired to
these primitives.
