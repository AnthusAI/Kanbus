import * as React from "react";
import { Layout, Section, Hero } from "../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

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
          <Card className="p-6 md:p-8 shadow-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">project/ layout</h3>
            </CardHeader>
            <CardContent className="p-0">
              <pre className="block overflow-x-auto rounded-lg bg-card-muted p-4 text-sm text-foreground font-mono leading-relaxed">
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
            </CardContent>
          </Card>
        </Section>

        <Section
          title="CLI Reference"
          subtitle="The primary interface for interacting with Kanbus."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-2">
            <Card className="p-8 shadow-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Core Commands</h3>
              </CardHeader>
              <CardContent className="p-0">
                <ul className="list-disc pl-4 mt-2 space-y-2 text-muted">
                <li>
                  <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">
                    kanbus init
                  </code>{" "}
                  - Initialize a new project
                </li>
                <li>
                  <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">
                    kanbus create
                  </code>{" "}
                  - Create a new issue
                </li>
                <li>
                  <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">
                    kanbus list
                  </code>{" "}
                  - List and filter issues
                </li>
                <li>
                  <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">
                    kanbus show [ID]
                  </code>{" "}
                  - Display issue details
                </li>
              </ul>
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Workflow</h3>
              </CardHeader>
              <CardContent className="p-0">
                <ul className="list-disc pl-4 mt-2 space-y-2 text-muted">
                <li>
                  <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">
                    kanbus update [ID]
                  </code>{" "}
                  - Modify status or fields
                </li>
                <li>
                  <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">
                    kanbus comment [ID]
                  </code>{" "}
                  - Add a comment
                </li>
                <li>
                  <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">
                    kanbus close [ID]
                  </code>{" "}
                  - Close an issue
                </li>
                <li>
                  <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">
                    kanbus wiki
                  </code>{" "}
                  - Render wiki templates
                </li>
              </ul>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Configuration"
          subtitle="Customize Kanbus to fit your team's process."
        >
          <Card className="p-8 shadow-card space-y-4">
            <CardHeader className="p-0 space-y-2">
              <h3 className="text-xl font-bold text-foreground">kanbus.yml</h3>
              <p className="text-muted leading-relaxed">
                The configuration file defines your issue hierarchy (Epic vs Task), workflow states (Todo, In
                Progress, Done), and other project defaults.
              </p>
            </CardHeader>
            <CardContent className="p-0">
              <pre className="block overflow-x-auto rounded-lg bg-card-muted p-4 text-sm text-foreground font-mono leading-relaxed">
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
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default DocsPage;
