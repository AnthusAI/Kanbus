import * as React from "react";
import { Layout, Section, Hero } from "../components";

const DocsPage = () => {
  return (
    <Layout>
      <Hero
        title="Documentation"
        subtitle="Everything you need to know about the Kanbus file structure and CLI."
        eyebrow="Reference"
      />

      <div className="space-y-12">
        <Section
          title="Directory Structure"
          subtitle="Kanbus keeps everything in a dedicated folder in your repository root."
        >
          <div className="w-full">
            <pre className="block overflow-x-auto rounded-xl bg-slate-100 dark:bg-slate-800 p-6 text-sm text-slate-800 dark:text-slate-200 font-mono leading-relaxed border border-slate-200 dark:border-slate-700">
              {`project/
├── .kanbus/               # Hidden configuration and state
│   ├── kanbus.yml         # Project-level configuration
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
          subtitle="The primary interface for interacting with Kanbus."
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
                    kanbus init
                  </code>{" "}
                  - Initialize a new project
                </li>
                <li>
                  <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-900 dark:text-slate-200">
                    kanbus create
                  </code>{" "}
                  - Create a new issue
                </li>
                <li>
                  <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-900 dark:text-slate-200">
                    kanbus list
                  </code>{" "}
                  - List and filter issues
                </li>
                <li>
                  <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-900 dark:text-slate-200">
                    kanbus show [ID]
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
                    kanbus update [ID]
                  </code>{" "}
                  - Modify status or fields
                </li>
                <li>
                  <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-900 dark:text-slate-200">
                    kanbus comment [ID]
                  </code>{" "}
                  - Add a comment
                </li>
                <li>
                  <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-900 dark:text-slate-200">
                    kanbus close [ID]
                  </code>{" "}
                  - Close an issue
                </li>
                <li>
                  <code className="rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-xs font-medium text-slate-900 dark:text-slate-200">
                    kanbus wiki
                  </code>{" "}
                  - Render wiki templates
                </li>
              </ul>
            </div>
          </div>
        </Section>

        <Section
          title="Configuration"
          subtitle="Customize Kanbus to fit your team's process."
        >
          <div className="w-full">
            <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
              kanbus.yml
            </h3>
            <p className="mb-4 text-slate-600 dark:text-slate-400 leading-relaxed">
              The configuration file defines your issue hierarchy (Epic vs Task),
              workflow states (Todo, In Progress, Done), and other project
              defaults.
            </p>
            <pre className="block overflow-x-auto rounded-xl bg-slate-100 dark:bg-slate-800 p-6 text-sm text-slate-800 dark:text-slate-200 font-mono leading-relaxed border border-slate-200 dark:border-slate-700">
{`project:
  key: KANB
  name: Kanbus Project

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
    </Layout>
  );
};

export default DocsPage;
