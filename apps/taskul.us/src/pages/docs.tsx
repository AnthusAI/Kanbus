import * as React from "react";
import { Layout, Section, Hero } from "../components";

const DocsPage = () => {
  return (
    <Layout>
      <div className="page">
        <div className="container">
          <Hero
            title="Documentation"
            subtitle="Everything you need to know about the Taskulus file structure and CLI."
            eyebrow="Reference"
          />
        </div>

        <div className="container grid">
          <Section
            title="Directory Structure"
            subtitle="Taskulus keeps everything in a dedicated folder in your repository root."
          >
            <div className="card full-width">
              <pre className="code-block">
{`project/
├── .taskulus/               # Hidden configuration and state
│   ├── config.yaml          # Project-level configuration
│   └── state.json           # Local cache (gitignored)
├── issues/                  # The database of issues
│   ├── tskl-001.json
│   ├── tskl-002.json
│   └── ...
└── wiki/                    # Planning documents
    ├── roadmap.md.j2        # Jinja2 template
    └── architecture.md      # Static markdown`}
              </pre>
            </div>
          </Section>

          <Section
            title="CLI Reference"
            subtitle="The primary interface for interacting with Taskulus."
            variant="alt"
          >
            <div className="grid two">
              <div className="card">
                <h3>Core Commands</h3>
                <ul className="list-disc pl-4 mt-2 space-y-2 text-slate-300">
                  <li><code>tsk init</code> - Initialize a new project</li>
                  <li><code>tsk create</code> - Create a new issue</li>
                  <li><code>tsk list</code> - List and filter issues</li>
                  <li><code>tsk show [ID]</code> - Display issue details</li>
                </ul>
              </div>
              <div className="card">
                <h3>Workflow</h3>
                <ul className="list-disc pl-4 mt-2 space-y-2 text-slate-300">
                  <li><code>tsk update [ID]</code> - Modify status or fields</li>
                  <li><code>tsk comment [ID]</code> - Add a comment</li>
                  <li><code>tsk close [ID]</code> - Close an issue</li>
                  <li><code>tsk wiki</code> - Render wiki templates</li>
                </ul>
              </div>
            </div>
          </Section>

          <Section
            title="Configuration"
            subtitle="Customize Taskulus to fit your team's process."
          >
            <div className="card full-width">
              <h3>config.yaml</h3>
              <p className="mb-4">
                The configuration file defines your issue hierarchy (Epic vs Task),
                workflow states (Todo, In Progress, Done), and other project defaults.
              </p>
              <pre className="code-block">
{`project:
  key: TSKL
  name: Taskulus Project

hierarchy:
  epic:
    color: blue
  task:
    parent: epic
    color: green

workflow:
  todo: { type: initial }
  in_progress: { type: active }
  done: { type: final }`}
              </pre>
            </div>
          </Section>
        </div>
      </div>
    </Layout>
  );
};

export default DocsPage;
