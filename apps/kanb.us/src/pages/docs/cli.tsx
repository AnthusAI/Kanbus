import * as React from "react";
import { DocsLayout } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { PageProps } from "gatsby";

const DocsCliPage = ({ location }: PageProps) => {
  return (
    <DocsLayout currentPath={location.pathname}>
      <div className="space-y-8">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground tracking-tight">CLI Reference</h1>
          <p className="mt-4 text-xl text-muted leading-relaxed">
            The primary interface for interacting with Kanbus.
          </p>
        </div>

        <div className="grid gap-8 md:grid-cols-2">
          <Card className="p-8">
            <CardHeader className="p-0 mb-3">
              <h3 className="text-xl font-bold text-foreground">Core Commands</h3>
            </CardHeader>
            <CardContent className="p-0">
              <ul className="list-disc pl-4 mt-2 space-y-3 text-muted">
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
          
          <Card className="p-8">
            <CardHeader className="p-0 mb-3">
              <h3 className="text-xl font-bold text-foreground">Workflow</h3>
            </CardHeader>
            <CardContent className="p-0">
              <ul className="list-disc pl-4 mt-2 space-y-3 text-muted">
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
      </div>
    </DocsLayout>
  );
};

export default DocsCliPage;
