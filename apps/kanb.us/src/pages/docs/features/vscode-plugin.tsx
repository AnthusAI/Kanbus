import * as React from "react";
import { DocsLayout } from "../../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { PageProps } from "gatsby";

const DocsVSCodePluginPage = ({ location }: PageProps) => {
  return (
    <DocsLayout currentPath={location.pathname}>
      <div className="space-y-8">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground tracking-tight">VS Code Plugin</h1>
          <p className="mt-4 text-xl text-muted leading-relaxed">
            Manage your project tasks natively without ever leaving your editor.
          </p>
        </div>

        <div className="mt-6">
          <a 
            href="/features/vscode-plugin" 
            className="inline-flex items-center gap-2 text-sm text-muted hover:text-foreground transition-colors"
          >
            <span>←</span>
            <span>Back to VS Code Plugin feature page</span>
          </a>
        </div>

        <div className="prose prose-slate dark:prose-invert max-w-none text-muted leading-relaxed space-y-6">
          <p>
            The Kanbus VS Code extension brings the powerful Kanban board directly into your editor as a webview tab. This allows you to view and interact with your tasks completely in context with the code you are writing.
          </p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Installation
          </h2>
          <p>
            You can install the extension directly from the VS Code Marketplace. Search for <strong>"Kanbus Board"</strong> (publisher: "kanbus").
          </p>
          <p>
            The extension comes bundled with the <code>kbsc</code> background server binary, so there is no separate server installation required.
          </p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Usage
          </h2>
          <p>To start using the extension, your workspace must already contain an initialized Kanbus project (i.e. a <code>.kanbus.yml</code> file). Once initialized:</p>
          <ol className="list-decimal pl-5 space-y-2 mt-4">
            <li>Open the workspace containing your Kanbus project in VS Code.</li>
            <li>Open the Command Palette (<code>Cmd+Shift+P</code> on Mac, <code>Ctrl+Shift+P</code> on Windows/Linux).</li>
            <li>Search for and run: <strong><code>Kanbus: Open Board</code></strong>.</li>
            <li>A new VS Code tab will open showing your Kanban board, which updates in real-time if you use the Kanbus CLI externally.</li>
          </ol>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Configuration
          </h2>
          <p>
            The extension handles most things automatically, but you can configure the internal port used by the bundled server if you have conflicts.
          </p>
          <ul className="list-disc pl-5 space-y-2 mt-4">
            <li><strong><code>kanbus.port</code></strong>: Sets the internal server port. The default is <code>0</code>, which tells the extension to automatically select a free port.</li>
          </ul>
        </div>
      </div>
    </DocsLayout>
  );
};

export default DocsVSCodePluginPage;
