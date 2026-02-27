import React from "react";
import { Layout } from "../../components/Layout";
import { FullVideoPlayer } from "../../components/FullVideoPlayer";
import { getVideoById } from "../../content/videos";

const PolicyAsCodePage = () => {
  const video = getVideoById("policy-as-code");

  return (
    <Layout title="Policy as Code - Kanbus" description="Define project rules using Gherkin BDD syntax. Enforce workflows, validations, and standards automatically.">
      <div className="content-page">
        <div className="content-header">
          <div className="eyebrow">New Feature</div>
          <h1>Policy as Code</h1>
          <p className="lead">
            Define project rules using Gherkin BDD syntax. Enforce workflows, validations, and standards automatically.
          </p>
        </div>

        {video && (
          <div className="video-section">
            <FullVideoPlayer video={video} />
          </div>
        )}

        <div className="content-body">
          <section>
            <h2>Git-Style Hooks for Issue Management</h2>
            <p>
              Just like Git hooks enforce commit standards, Kanbus policies enforce issue management standards. 
              Create <code>.policy</code> files that automatically validate transitions, enforce required fields, 
              and maintain project consistency.
            </p>
          </section>

          <section>
            <h2>Write Policies in Gherkin</h2>
            <p>
              Use familiar BDD syntax to describe your project rules. No programming required—just clear, 
              readable scenarios that express exactly what should happen.
            </p>
            <pre><code>{`Feature: Tasks require assignee

  Scenario: Task must have assignee to start
    Given the issue type is "task"
    When transitioning to "in_progress"
    Then the issue must have field "assignee"`}</code></pre>
          </section>

          <section>
            <h2>Automatic Enforcement</h2>
            <p>
              Policies run automatically on every issue create and update. When a policy fails, 
              the operation is rejected with a clear error message showing exactly which rule was violated.
            </p>
            <pre><code>{`$ kbs update task-123 --status in_progress

Error: policy violation in require-assignee.policy
  Scenario: Task must have assignee to start
  Failed: Then the issue must have field "assignee"
  issue does not have field "assignee" set`}</code></pre>
          </section>

          <section>
            <h2>Rich Step Library</h2>
            <p>
              Built-in steps cover common scenarios out of the box:
            </p>
            <ul>
              <li><strong>Field validation:</strong> Require assignee, description, labels</li>
              <li><strong>Status transitions:</strong> Control when issues can move between states</li>
              <li><strong>Hierarchy rules:</strong> Enforce parent-child relationships</li>
              <li><strong>Custom patterns:</strong> Validate titles, descriptions with regex</li>
              <li><strong>Aggregate checks:</strong> Ensure all children meet criteria before parent transitions</li>
            </ul>
          </section>

          <section>
            <h2>Examples</h2>
            
            <h3>Require Description for Bugs</h3>
            <pre><code>{`Feature: Bug reporting standards

  Scenario: Bugs must have detailed description
    Given the issue type is "bug"
    When creating an issue
    Then the description must not be empty`}</code></pre>

            <h3>Epic Completion Rules</h3>
            <pre><code>{`Feature: Epic workflow

  Scenario: Epic can only close when all children are done
    Given the issue type is "epic"
    When transitioning to "closed"
    Then all child issues must have status "closed"`}</code></pre>

            <h3>Title Conventions</h3>
            <pre><code>{`Feature: Naming conventions

  Scenario: Bugs must have BUG prefix
    Given the issue type is "bug"
    Then the title must match pattern "^BUG-"`}</code></pre>
          </section>

          <section>
            <h2>CLI Tools</h2>
            <p>
              Test and validate policies before they affect your team:
            </p>
            <pre><code>{`# Check policies against a specific issue
kbs policy check task-123

# List all loaded policies
kbs policy list

# Validate policy file syntax
kbs policy validate`}</code></pre>
          </section>

          <section>
            <h2>Zero Configuration</h2>
            <p>
              Just create a <code>policies/</code> directory in your project and add <code>.policy</code> files. 
              Kanbus automatically discovers and evaluates them. No config files, no registration, no setup.
            </p>
          </section>

          <section>
            <h2>Built for Teams and Agents</h2>
            <p>
              Policies work the same whether a human or an AI agent is managing issues. Define your standards 
              once, and they're enforced consistently across all interactions—CLI, console UI, and programmatic access.
            </p>
          </section>
        </div>
      </div>
    </Layout>
  );
};

export default PolicyAsCodePage;
