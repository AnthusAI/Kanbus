import React from "react";
import { DocsLayout, CodeBlock } from "../../../components";

const LifecycleHooksDocsPage = () => {
  return (
    <DocsLayout title="Lifecycle Hooks" description="Project-defined integrations on Kanbus lifecycle events">
      <div className="docs-content">
        <h1>Lifecycle Hooks</h1>
        <p className="lead">
          Lifecycle hooks make Kanbus command boundaries programmable. Projects attach external logic
          to before/after events without forking CLI behavior.
        </p>

        <h2>Event Coverage (v1)</h2>
        <ul>
          <li><code>issue.create</code></li>
          <li><code>issue.update</code></li>
          <li><code>issue.close</code></li>
          <li><code>issue.delete</code></li>
          <li><code>issue.comment</code></li>
          <li><code>issue.dependency</code></li>
          <li><code>issue.promote</code></li>
          <li><code>issue.localize</code></li>
          <li><code>issue.show</code></li>
          <li><code>issue.list</code></li>
          <li><code>issue.ready</code></li>
        </ul>

        <h2>Configuration</h2>
        <CodeBlock>
{`hooks:
  enabled: true
  run_in_beads_mode: true
  default_timeout_ms: 5000
  before:
    issue.update:
      - id: block-invalid
        command: ["./hooks/block-invalid.sh"]
        timeout_ms: 1200
  after:
    issue.create:
      - id: notify
        command: ["./hooks/notify.sh"]
        blocking: false
        env:
          WEBHOOK_URL: "https://example.invalid/hooks"`}
        </CodeBlock>

        <h2>Execution Model</h2>
        <ul>
          <li>Payload is JSON on <code>stdin</code>.</li>
          <li>Before-hooks on mutating events are fail-closed by default.</li>
          <li>After-hooks are observer style; failures emit warnings and do not fail the command.</li>
          <li><code>timeout_ms</code>, <code>blocking</code>, <code>cwd</code>, and <code>env</code> can be set per hook.</li>
        </ul>

        <h2>Payload Contract</h2>
        <CodeBlock>
{`{
  "schema_version": "kanbus.hooks.v1",
  "phase": "after",
  "event": "issue.create",
  "timestamp": "2026-03-08T16:31:44.021Z",
  "actor": "dev@example.com",
  "mode": {
    "beads_mode": false,
    "project_root": "/repo",
    "working_directory": "/repo",
    "runtime": "python|rust"
  },
  "operation": {
    "issue": { "identifier": "kanbus-abc123", "title": "..." }
  }
}`}
        </CodeBlock>

        <h2>Policy Integration</h2>
        <p>
          Policy guidance is implemented as a built-in lifecycle hook provider. Existing policy DSL behavior is unchanged.
          Use <code>--no-guidance</code> or <code>KANBUS_NO_GUIDANCE</code> to suppress only policy guidance while keeping
          external hooks active.
        </p>

        <h2>CLI Operations</h2>
        <CodeBlock>
{`kbs hooks list
kbs hooks validate
kbs --no-hooks list
KANBUS_NO_HOOKS=1 kbs list`}
        </CodeBlock>
      </div>
    </DocsLayout>
  );
};

export default LifecycleHooksDocsPage;
