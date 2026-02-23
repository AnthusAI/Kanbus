import * as React from "react";
import { Layout, Section, Hero, CodeBlock } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const VSCodePluginPage = () => {
  return (
    <Layout>
      <Hero
        title="VS Code Integration"
        subtitle="Manage your project without leaving your code. The full Kanbus experience, embedded in your editor."
        eyebrow="Integrations"
      />

      <div className="space-y-12">
        <Section
          title="Seamless Workflow"
          subtitle="A dedicated Kanban board inside VS Code."
        >
          <div className="space-y-8">
            <Card className="p-8 shadow-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Zero Context Switching</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
                <p>
                  Open your project board in a VS Code tab. Drag issues, edit details, and filter tasks 
                  while your code remains visible in the next pane. No more alt-tabbing to the browser.
                </p>
                <div className="rounded-xl overflow-hidden shadow-lg border border-border/50 aspect-video bg-card/50 flex items-center justify-center">
                  <span className="text-muted font-medium">Screenshot: Board in VS Code Tab</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Code & Context"
          subtitle="Link your work directly to your files."
          variant="alt"
        >
          <div className="grid gap-6 md:grid-cols-2">
            <Card className="p-8 shadow-card bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Quick Access</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Access the board from the Activity Bar or Command Palette.
                </p>
                <CodeBlock label="Command Palette">
                  {'Kanbus: Open Board'}
                </CodeBlock>
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">File Navigation</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Click an issue ID in a comment or commit message to jump straight to the details.
                  (Coming soon: Jump from issue to relevant code files).
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Get Started"
          subtitle="Install from the Marketplace."
        >
           <Card className="p-8 shadow-card">
            <div className="flex flex-col items-center text-center space-y-6">
              <div className="rounded-xl overflow-hidden shadow-lg border border-border/50 aspect-[2/1] w-full max-w-lg bg-card/50 flex items-center justify-center">
                <span className="text-muted font-medium">Screenshot: Extension Marketplace Page</span>
              </div>
              <p className="text-muted max-w-lg">
                The Kanbus extension is open source and available for free.
              </p>
              <a 
                href="#" 
                className="rounded-full bg-selected px-6 py-3 text-sm font-semibold text-background shadow-card hover:brightness-95 transition-all"
              >
                Install for VS Code
              </a>
            </div>
           </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default VSCodePluginPage;
