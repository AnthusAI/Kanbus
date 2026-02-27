import * as React from "react";
import { DocsLayout } from "../../components";
import { CodeBlock } from "../../components/CodeBlock";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { PageProps } from "gatsby";

const DocsConfigurationPage = ({ location }: PageProps) => {
  return (
    <DocsLayout currentPath={location.pathname}>
      <div className="space-y-8">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground tracking-tight">Configuration</h1>
          <p className="mt-4 text-xl text-muted leading-relaxed">
            Customize Kanbus to fit your team's process.
          </p>
        </div>

        <Card className="p-8 space-y-4">
          <CardHeader className="p-0 space-y-2">
            <h3 className="text-xl font-bold text-foreground">kanbus.yml</h3>
            <p className="text-muted leading-relaxed">
              The configuration file defines your issue hierarchy (Epic vs Task), workflow states (Todo, In
              Progress, Done), and other project defaults.
            </p>
          </CardHeader>
          <CardContent className="p-0 mt-4">
            <CodeBlock>
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
            </CodeBlock>
          </CardContent>
        </Card>
      </div>
    </DocsLayout>
  );
};

export default DocsConfigurationPage;
