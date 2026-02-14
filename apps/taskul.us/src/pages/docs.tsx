import * as React from "react";
import { Layout, Section, Hero } from "../components";

const DocsPage = () => {
  return (
    <Layout>
      <Hero
        title="Documentation"
        subtitle="Everything you need to know about the Taskulus file structure and CLI."
        eyebrow="Reference"
      />

      <div className="space-y-12">
        <Section
          title="Directory Structure"
          subtitle="Taskulus keeps everything in a dedicated folder in your repository root."
        >
          <div className="w-full">
            <pre className="block overflow-x-auto rounded-xl bg-slate-100 dark:bg-slate-800 p-6 text-sm text-slate-800 dark:text-slate-200 font-mono leading-relaxed border border-slate-200 dark:border-slate-700">
              {`project/
├── config.yaml              # Project-level configuration
├── issues/                  # Issue JSON files
│   ├── tskl-001.json
│   ├── tskl-002.json
│   └── ...
├── wiki/                    # Planning documents
│   ├── roadmap.md.j2        # Jinja2 template
│   └── architecture.md      # Static markdown
└── .cache/                  # Derived index data (gitignored)
.taskulus.yml                # Repo-level configuration
.taskulus.override.yml       # Optional local overrides (gitignored)`}
            </pre>
          </div>
        </Section>

        <Section
          title="CLI Reference"
          subtitle="The primary interface for interacting with Taskulus."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Core Commands
              </h3>
              <ul className="list-disc pl-4 mt-2 space-y-2 text-slate-600 dark:text-slate-400">
                <li>
                  <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-900 dark:text-slate-200">
                    tsk init
                  </code>{" "}
                  - Initialize a new project
                </li>
                <li>
                  <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-900 dark:text-slate-200">
                    tsk create
                  </code>{" "}
                  - Create a new issue
                </li>
                <li>
                  <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-900 dark:text-slate-200">
                    tsk list
                  </code>{" "}
                  - List and filter issues
                </li>
                <li>
                  <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-900 dark:text-slate-200">
                    tsk show [ID]
                  </code>{" "}
                  - Display issue details
                </li>
              </ul>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Workflow
              </h3>
              <ul className="list-disc pl-4 mt-2 space-y-2 text-slate-600 dark:text-slate-400">
                <li>
                  <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-900 dark:text-slate-200">
                    tsk update [ID]
                  </code>{" "}
                  - Modify status or fields
                </li>
                <li>
                  <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-900 dark:text-slate-200">
                    tsk comment [ID]
                  </code>{" "}
                  - Add a comment
                </li>
                <li>
                  <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-900 dark:text-slate-200">
                    tsk close [ID]
                  </code>{" "}
                  - Close an issue
                </li>
                <li>
                  <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-900 dark:text-slate-200">
                    tsk wiki
                  </code>{" "}
                  - Render wiki templates
                </li>
              </ul>
            </div>
          </div>
        </Section>

        <Section
          title="Configuration"
          subtitle="Customize Taskulus to fit your team's process."
        >
          <div className="w-full">
            <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
              Configuration Files
            </h3>
            <p className="mb-4 text-slate-600 dark:text-slate-400 leading-relaxed">
              Taskulus uses a repo-level configuration file and a project-level
              configuration file. The repo-level file controls discovery and
              defaults. The project-level file controls hierarchy, workflows,
              and type rules.
            </p>
            <pre className="block overflow-x-auto rounded-xl bg-slate-100 dark:bg-slate-800 p-6 text-sm text-slate-800 dark:text-slate-200 font-mono leading-relaxed border border-slate-200 dark:border-slate-700">
              {`.taskulus.yml
project_directory: project
external_projects: []
project_key: tsk

project/config.yaml
prefix: tsk
hierarchy: [initiative, epic, task, sub-task]
types: [bug, story, chore]
workflows:
  default:
    open: [in_progress, closed, deferred]
initial_status: open
priorities:
  0: critical
  1: high
  2: medium
  3: low
  4: trivial
default_priority: 2`}
            </pre>
          </div>
        </Section>

        <Section
          title="Setup and Updates"
          subtitle="Initialize Taskulus once, then evolve the configuration over time."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                First-Time Setup
              </h3>
              <ol className="list-decimal pl-5 mt-2 space-y-2 text-slate-600 dark:text-slate-400">
                <li>Initialize a git repository.</li>
                <li>Run <code>tsk init</code> from the repo root.</li>
                <li>Confirm <code>project/</code> and <code>.taskulus.yml</code> exist.</li>
              </ol>
              <pre className="mt-4 block overflow-x-auto rounded-xl bg-slate-100 dark:bg-slate-800 p-4 text-xs text-slate-800 dark:text-slate-200 font-mono leading-relaxed border border-slate-200 dark:border-slate-700">
                {`git init
tsk init`}
              </pre>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Update Over Time
              </h3>
              <ul className="list-disc pl-4 mt-2 space-y-2 text-slate-600 dark:text-slate-400">
                <li>Edit <code>project/config.yaml</code> to change hierarchy, workflows, and priorities.</li>
                <li>Edit <code>.taskulus.yml</code> to add external projects or change the project directory.</li>
                <li>Use <code>.taskulus.override.yml</code> for local-only defaults like assignee or time zone.</li>
                <li>Run <code>tsk list</code> to confirm the config is still valid.</li>
              </ul>
            </div>
          </div>
          <div className="mt-8 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
            <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
              Beads Compatibility Mode (Transition)
            </h3>
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
              If you are transitioning from Beads JSONL, enable compatibility in
              both config files and keep the <code>.beads/</code> directory in
              your repo.
            </p>
            <pre className="mt-4 block overflow-x-auto rounded-xl bg-slate-100 dark:bg-slate-800 p-4 text-xs text-slate-800 dark:text-slate-200 font-mono leading-relaxed border border-slate-200 dark:border-slate-700">
              {`.taskulus.yml
beads_compatibility: true

project/config.yaml
beads_compatibility: true`}
            </pre>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default DocsPage;
