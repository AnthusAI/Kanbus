import React from "react";
import { DocsLayout, CodeBlock } from "../../../components";

const PolicyAsCodeDocsPage = () => {
  return (
    <DocsLayout title="Policy as Code" description="Enforce project rules automatically using Gherkin BDD syntax">
      <div className="docs-content">
        <h1>Policy as Code</h1>
        <p className="lead">
          Enforce project rules automatically using Gherkin BDD syntax. Define workflows, validations, 
          and standards that apply to all issue operations.
        </p>

        <h2>Overview</h2>
        <p>
          Policy as Code brings Git-style hooks to Kanbus issue management. Create <code>.policy</code> files 
          using familiar Gherkin syntax to define rules that are automatically enforced on every issue create, 
          update, and transition.
        </p>

        <h2>Getting Started</h2>
        <p>
          Create a <code>policies/</code> directory in your project root (next to <code>.kanbus.yml</code>):
        </p>
        <CodeBlock>
{`project/
├── .kanbus.yml
├── issues/
└── policies/
    ├── require-assignee.policy
    └── epic-workflow.policy`}
        </CodeBlock>

        <h2>Policy File Format</h2>
        <p>
          Policy files use standard Gherkin syntax with <code>.policy</code> extension:
        </p>
        <CodeBlock>
{`Feature: Tasks require assignee

  Scenario: Task must have assignee to start
    Given the issue type is "task"
    When transitioning to "in_progress"
    Then the issue must have field "assignee"`}
        </CodeBlock>

        <h3>Step Types</h3>
        <ul>
          <li><strong>Given:</strong> Filter which issues this scenario applies to</li>
          <li><strong>When:</strong> Filter by operation type or transition</li>
          <li><strong>Then:</strong> Assert requirements that must be met</li>
        </ul>

        <h3>Scenario Skipping</h3>
        <p>
          If any <code>Given</code> or <code>When</code> step doesn't match, the entire scenario is skipped. 
          This allows you to write targeted policies that only apply to specific situations.
        </p>

        <h2>Built-in Steps</h2>

        <h3>Given Steps (Filters)</h3>
        <table>
          <thead>
            <tr>
              <th>Step</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><code>the issue type is "TYPE"</code></td>
              <td>Filter by issue type</td>
            </tr>
            <tr>
              <td><code>the issue has label "LABEL"</code></td>
              <td>Filter by label presence</td>
            </tr>
            <tr>
              <td><code>the issue has a parent</code></td>
              <td>Filter issues with parents</td>
            </tr>
            <tr>
              <td><code>the issue priority is N</code></td>
              <td>Filter by priority level</td>
            </tr>
          </tbody>
        </table>

        <h3>When Steps (Triggers)</h3>
        <table>
          <thead>
            <tr>
              <th>Step</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><code>transitioning to "STATUS"</code></td>
              <td>Filter by target status</td>
            </tr>
            <tr>
              <td><code>transitioning from "STATUS"</code></td>
              <td>Filter by source status</td>
            </tr>
            <tr>
              <td><code>transitioning from "A" to "B"</code></td>
              <td>Filter specific transition</td>
            </tr>
            <tr>
              <td><code>creating an issue</code></td>
              <td>Filter create operations</td>
            </tr>
            <tr>
              <td><code>closing an issue</code></td>
              <td>Filter close operations</td>
            </tr>
          </tbody>
        </table>

        <h3>Then Steps (Assertions)</h3>
        <table>
          <thead>
            <tr>
              <th>Step</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><code>the issue must have field "FIELD"</code></td>
              <td>Require field is set</td>
            </tr>
            <tr>
              <td><code>the issue must not have field "FIELD"</code></td>
              <td>Require field is not set</td>
            </tr>
            <tr>
              <td><code>the field "FIELD" must be "VALUE"</code></td>
              <td>Require specific value</td>
            </tr>
            <tr>
              <td><code>all child issues must have status "STATUS"</code></td>
              <td>Check all children</td>
            </tr>
            <tr>
              <td><code>no child issues may have status "STATUS"</code></td>
              <td>Forbid child status</td>
            </tr>
            <tr>
              <td><code>the parent issue must have status "STATUS"</code></td>
              <td>Check parent status</td>
            </tr>
            <tr>
              <td><code>the issue must have at least N labels</code></td>
              <td>Minimum label count</td>
            </tr>
            <tr>
              <td><code>the issue must have label "LABEL"</code></td>
              <td>Require specific label</td>
            </tr>
            <tr>
              <td><code>the description must not be empty</code></td>
              <td>Require description</td>
            </tr>
            <tr>
              <td><code>the title must match pattern "REGEX"</code></td>
              <td>Validate title format</td>
            </tr>
          </tbody>
        </table>

        <h2>Common Patterns</h2>

        <h3>Require Assignee for Active Work</h3>
        <CodeBlock>
{`Feature: Work assignment

  Scenario: In-progress tasks need assignee
    Given the issue type is "task"
    When transitioning to "in_progress"
    Then the issue must have field "assignee"`}
        </CodeBlock>

        <h3>Epic Completion Workflow</h3>
        <CodeBlock>
{`Feature: Epic lifecycle

  Scenario: Epic requires all children closed
    Given the issue type is "epic"
    When transitioning to "closed"
    Then all child issues must have status "closed"

  Scenario: Epic cannot have blocked children
    Given the issue type is "epic"
    Then no child issues may have status "blocked"`}
        </CodeBlock>

        <h3>Bug Reporting Standards</h3>
        <CodeBlock>
{`Feature: Bug quality

  Scenario: Bugs need description
    Given the issue type is "bug"
    When creating an issue
    Then the description must not be empty

  Scenario: Bugs need BUG prefix
    Given the issue type is "bug"
    Then the title must match pattern "^BUG-"

  Scenario: High priority bugs need review
    Given the issue type is "bug"
    Given the issue priority is 0
    When transitioning to "closed"
    Then the issue must have label "reviewed"`}
        </CodeBlock>

        <h3>Parent-Child Coordination</h3>
        <CodeBlock>
{`Feature: Hierarchy rules

  Scenario: Child cannot start before parent
    Given the issue has a parent
    When transitioning to "in_progress"
    Then the parent issue must have status "in_progress"`}
        </CodeBlock>

        <h2>CLI Commands</h2>

        <h3>Check Policies</h3>
        <p>Test policies against a specific issue without modifying it:</p>
        <CodeBlock>
{`kbs policy check task-123`}
        </CodeBlock>

        <h3>List Policies</h3>
        <p>Show all loaded policy files and their scenarios:</p>
        <CodeBlock>
{`kbs policy list`}
        </CodeBlock>

        <h3>Validate Policies</h3>
        <p>Check policy file syntax without running them:</p>
        <CodeBlock>
{`kbs policy validate`}
        </CodeBlock>

        <h2>Error Messages</h2>
        <p>
          When a policy fails, Kanbus shows exactly which rule was violated:
        </p>
        <CodeBlock>
{`$ kbs update task-123 --status in_progress

Error: policy violation in require-assignee.policy
  Scenario: Task must have assignee to start
  Failed: Then the issue must have field "assignee"
  issue does not have field "assignee" set`}
        </CodeBlock>

        <h2>Best Practices</h2>

        <h3>One Policy Per File</h3>
        <p>
          Keep related scenarios together in a single file, but separate different concerns 
          into different files for clarity.
        </p>

        <h3>Use Descriptive Names</h3>
        <p>
          Feature and scenario names appear in error messages. Make them clear and actionable.
        </p>

        <h3>Test Before Deploying</h3>
        <p>
          Use <code>kbs policy check</code> to test policies against existing issues before 
          committing them to your repository.
        </p>

        <h3>Start Permissive</h3>
        <p>
          Begin with warnings or optional checks, then tighten policies as your team adapts.
        </p>

        <h2>Performance</h2>
        <p>
          Policy evaluation is fast:
        </p>
        <ul>
          <li>Policies are only loaded when the <code>policies/</code> directory exists</li>
          <li>Scenarios skip early when filters don't match</li>
          <li>Native Gherkin parsing with minimal overhead</li>
          <li>No external process spawning or network calls</li>
        </ul>

        <h2>Limitations</h2>
        <ul>
          <li>Policies cannot modify issues, only accept or reject operations</li>
          <li>No custom step definitions (use built-in steps only)</li>
          <li>Policies run synchronously, blocking the operation</li>
          <li>No notification or logging hooks (only accept/reject)</li>
        </ul>
      </div>
    </DocsLayout>
  );
};

export default PolicyAsCodeDocsPage;
