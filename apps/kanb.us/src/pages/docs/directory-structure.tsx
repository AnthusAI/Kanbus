import * as React from "react";
import { DocsLayout } from "../../components";
import { CodeBlock } from "../../components/CodeBlock";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { PageProps } from "gatsby";

const DocsDirectoryStructurePage = ({ location }: PageProps) => {
  return (
    <DocsLayout currentPath={location.pathname}>
      <div className="space-y-8">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground tracking-tight">Directory Structure</h1>
          <p className="mt-4 text-xl text-muted leading-relaxed">
            Kanbus keeps everything in a dedicated folder in your repository root.
          </p>
        </div>

        <Card className="p-6 md:p-8">
          <CardHeader className="p-0 mb-4">
            <h3 className="text-xl font-bold text-foreground">project/ layout</h3>
          </CardHeader>
          <CardContent className="p-0">
            <CodeBlock>
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
            </CodeBlock>
          </CardContent>
        </Card>
      </div>
    </DocsLayout>
  );
};

export default DocsDirectoryStructurePage;
