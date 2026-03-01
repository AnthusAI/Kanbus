import React from "react";
import { DocsLayout, CodeBlock } from "../../../components";

const PolicyAsCodeDocsPage = () => {
  return (
    <DocsLayout title="Policy as Code" description="Guardrails plus kairotic guidance for Kanbus issue workflows">
      <div className="docs-content">
        <h1>Policy as Code</h1>
        <p className="lead">
          Policy as Code combines strict guardrails with in-the-moment guidance so agents follow procedure reliably while staying fast.
        </p>

        <h2>Kairos</h2>
        <p>
          This feature is explicitly about <strong>kairos</strong>: delivering the right instruction at the right moment. Instead of relying on
          a single upfront prompt and perfect model memory, Kanbus uses programmatic hooks to trigger guidance when context indicates it is
          relevant.
        </p>

        <h2>File Layout</h2>
        <CodeBlock>
{`project/
├── issues/
└── policies/
    ├── epic-ready.policy
    └── list-guidance.policy`}
        </CodeBlock>

        <h2>Core DSL</h2>
        <h3>Filters</h3>
        <ul>
          <li><code>When creating an issue</code></li>
          <li><code>When updating an issue</code></li>
          <li><code>When deleting an issue</code></li>
          <li><code>When viewing an issue</code></li>
          <li><code>When listing issues</code></li>
          <li><code>When listing ready issues</code></li>
          <li><code>When transitioning to "STATUS"</code></li>
          <li><code>When transitioning from "A" to "B"</code></li>
        </ul>

        <h3>Assertions</h3>
        <ul>
          <li><code>Then the issue must have field "FIELD"</code></li>
          <li><code>Then the field "FIELD" must be "VALUE"</code></li>
          <li><code>Then all child issues must have status "STATUS"</code></li>
          <li><code>Then the issue must have at least N child issues</code></li>
        </ul>

        <h3>Guidance Steps</h3>
        <ul>
          <li><code>Then warn "TEXT"</code></li>
          <li><code>Then suggest "TEXT"</code></li>
          <li><code>Then explain "TEXT"</code> (attaches as an <code>Explanation:</code> line under the previous emitted item)</li>
        </ul>

        <h2>Example: Epic Ready Guardrail</h2>
        <CodeBlock>
{`Feature: Epic readiness guardrail

  Scenario: Epic needs child issues before ready
    Given the issue type is "epic"
    When transitioning to "ready"
    Then the issue must have at least 1 child issues
    Then explain "Epics represent milestones composed of multiple child issues."
    Then warn "Create at least one child story or task before marking an epic ready."
    Then suggest "If this is one deliverable, model it as a story or task instead of an epic."`}
        </CodeBlock>

        <h2>Example: List-Level Guidance</h2>
        <CodeBlock>
{`Feature: Planning loop reminders

  Scenario: Keep statuses current
    When listing issues
    Then suggest "Remember to reflect your current status in issue states as you work."

  Scenario: Ready queue semantics
    When listing ready issues
    Then warn "Ready means unblocked and actionable now."`}
        </CodeBlock>

        <h2>Output Behavior</h2>
        <ul>
          <li>Blocking paths print policy violation details first.</li>
          <li>Guidance is emitted on stderr.</li>
          <li>Guidance ordering is warnings first, then suggestions.</li>
          <li>Explanations stay attached under their parent message.</li>
        </ul>

        <CodeBlock>
{`GUIDANCE WARNING: Ready means unblocked and actionable now.
GUIDANCE SUGGESTION: Remember to reflect your current status in issue states as you work.
  Explanation: Keeping statuses current improves handoff reliability.`}
        </CodeBlock>

        <h2>Hooks</h2>
        <p>Guidance hooks run after successful:</p>
        <ul>
          <li><code>show</code></li>
          <li><code>create</code></li>
          <li><code>update</code></li>
          <li><code>close</code></li>
          <li><code>delete</code></li>
          <li><code>list</code></li>
          <li><code>ready</code></li>
        </ul>

        <h2>CLI Commands</h2>
        <CodeBlock>
{`kbs policy list
kbs policy validate
kbs policy check <issue-id>
kbs policy guide <issue-id>

kbs --no-guidance list
KANBUS_NO_GUIDANCE=1 kbs show <issue-id>`}
        </CodeBlock>

        <h2>Validation Rules</h2>
        <ul>
          <li>Unknown steps fail validation.</li>
          <li>Orphan <code>explain</code> steps fail validation and evaluation.</li>
          <li>Policy parsing/validation errors are reported with file + scenario context.</li>
        </ul>
      </div>
    </DocsLayout>
  );
};

export default PolicyAsCodeDocsPage;
