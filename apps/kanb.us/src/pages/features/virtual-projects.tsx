import * as React from "react";
import { Layout, Section, Hero, CodeBlock } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const VirtualProjectsPage = () => {
  return (
    <Layout>
      <Hero
        title="Virtual Projects"
        subtitle="View and manage issues from multiple repositories in a single workspace."
        eyebrow="Features"
      />

      <div className="space-y-12">
        <Section
          title="One View, Many Projects"
          subtitle="Don't context switch between repositories."
        >
          <Card className="p-8 shadow-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Unified Workflow</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Kanbus allows you to mount other Kanbus projects into your current workspace as "virtual projects".
                This aggregates issues from all configured projects into a single list, so you can query, filter,
                and track work across your entire stack without changing directories.
              </p>
              <p>
                Virtual projects are perfect for:
              </p>
              <ul className="list-disc pl-5 space-y-1">
                <li>Microservices architectures where work spans multiple repos.</li>
                <li>Library authors tracking issues in both the library and the consuming app.</li>
                <li>Release managers overseeing multiple related projects.</li>
              </ul>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Shared Configuration"
          subtitle="Team-wide visibility via .kanbus.yml"
          variant="alt"
        >
          <div className="space-y-6">
            <Card className="p-8 shadow-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">For the Whole Team</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  To make a virtual project available to everyone working on the repository, add it to your
                  <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.kanbus.yml</code> configuration file.
                </p>
                <CodeBlock label=".kanbus.yml">
{`project_key: app
virtual_projects:
  api:
    path: ../backend-api
  ui:
    path: ../design-system`}
                </CodeBlock>
                <p>
                  Now, when anyone runs <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">kanbus list</code>,
                  they will see issues from the main project (project_key: app) alongside issues from the `api` and `ui` projects.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Local Overrides"
          subtitle="Private configurations for your personal workflow."
        >
          <div className="space-y-6">
            <Card className="p-8 shadow-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">.kanbus.override.yml</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Sometimes you need to see issues from a dependency that isn't part of the official project structure—for example,
                  debugging a library you're locally linking. You can add virtual projects just for yourself using a
                  <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.kanbus.override.yml</code> file.
                </p>
                <p>
                  This file is git-ignored by default, so your personal setup won't affect other team members.
                </p>
                <CodeBlock label=".kanbus.override.yml">
{`virtual_projects:
  my_lib:
    path: ../experimental-lib`}
                </CodeBlock>
                <p>
                  Kanbus merges this configuration with the main <code className="mx-1 px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-sm font-mono text-foreground">.kanbus.yml</code>,
                  giving you a super-set of all projects.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default VirtualProjectsPage;
