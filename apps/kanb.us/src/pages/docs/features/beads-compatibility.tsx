import * as React from "react";
import { DocsLayout, CodeBlock } from "../../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { PageProps } from "gatsby";

const DocsBeadsCompatibilityPage = ({ location }: PageProps) => {
  return (
    <DocsLayout currentPath={location.pathname}>
      <div className="space-y-8">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground tracking-tight">Beads Compatibility</h1>
          <p className="mt-4 text-xl text-muted leading-relaxed">
            Seamlessly interact with legacy Beads JSONL data without migrating.
          </p>
        </div>

        <div className="mt-6">
          <a 
            href="/features/beads-compatibility" 
            className="inline-flex items-center gap-2 text-sm text-muted hover:text-foreground transition-colors"
          >
            <span>←</span>
            <span>Back to Beads Compatibility feature page</span>
          </a>
        </div>

        <div className="prose prose-slate max-w-none text-muted leading-relaxed space-y-6">
          <p>
            Kanbus provides built-in compatibility with the older <strong>Beads</strong> format (which stores issues as a single <code>.beads/issues.jsonl</code> file). You do not need to migrate your data to use the Kanbus CLI or the Kanban board interface.
          </p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Enabling Beads Mode
          </h2>
          
          <h3 className="text-xl font-bold text-foreground mt-6 mb-2">Option 1: One-Time CLI Flag</h3>
          <p>You can use the <code>--beads</code> flag on any command to temporarily run in compatibility mode.</p>
          <CodeBlock label="Terminal">
{`kanbus --beads list
kanbus --beads show bdx-epic
kanbus --beads create "New issue" --parent bdx-epic`}
          </CodeBlock>

          <h3 className="text-xl font-bold text-foreground mt-6 mb-2">Option 2: Persistent Configuration</h3>
          <p>To avoid typing the flag constantly, enable it in your configuration files (<code>.kanbus.yml</code> or <code>project/config.yaml</code>):</p>
          <CodeBlock label="Terminal">
{`beads_compatibility: true`}
          </CodeBlock>
          <p className="mt-4">Once enabled, standard commands like <code>kanbus list</code> and <code>kanbus console</code> automatically read and write to <code>.beads/issues.jsonl</code>.</p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Supported Commands
          </h2>
          <p>When operating in beads mode, the following core features work as expected:</p>
          <ul className="list-disc pl-5 space-y-2 mt-4">
            <li><code>kanbus --beads list</code></li>
            <li><code>kanbus --beads ready</code></li>
            <li><code>kanbus --beads show &lt;id&gt;</code></li>
            <li><code>kanbus --beads create &lt;title&gt; [--parent &lt;id&gt;]</code></li>
            <li><code>kanbus --beads update &lt;id&gt; [--status &lt;status&gt;]</code></li>
            <li><code>kanbus --beads delete &lt;id&gt;</code></li>
            <li><code>kanbus --beads dep &lt;id&gt; [add|remove] &lt;type&gt; &lt;target&gt;</code></li>
          </ul>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Migration (Optional)
          </h2>
          <p>
            If you decide you want to permanently move away from the JSONL format to the modern <code>project/issues/</code> directory structure, Kanbus provides a one-way migration tool:
          </p>
          <CodeBlock label="Terminal">
{`kanbus migrate`}
          </CodeBlock>
          <p className="mt-4 text-sm italic">
            Note: You can stay in Beads format indefinitely. However, certain new features like Local filtering (<code>--no-local</code>) are not supported while in beads mode.
          </p>
        </div>
      </div>
    </DocsLayout>
  );
};

export default DocsBeadsCompatibilityPage;
