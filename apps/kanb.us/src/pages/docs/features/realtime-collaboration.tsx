import * as React from "react";
import { PageProps } from "gatsby";
import { DocsLayout, CodeBlock } from "../../../components";
import { getGitHubDocsSourceUrl, getMkDocsDocUrl } from "../../../lib/getMkDocsSrc";

const DocsRealtimeCollaborationPage = ({ location }: PageProps) => {
  const canonicalDocs = getMkDocsDocUrl("REALTIME");
  const sourceDocs = getGitHubDocsSourceUrl("docs/REALTIME.md");
  const docsHref = canonicalDocs ?? sourceDocs;
  const docsLabel = canonicalDocs ? "Open canonical MkDocs docs →" : "Open docs source on GitHub →";

  return (
    <DocsLayout currentPath={location.pathname}>
      <div className="space-y-8">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground tracking-tight">Realtime Collaboration</h1>
          <p className="mt-4 text-xl text-muted leading-relaxed">
            Gossip + overlay cache for distributed realtime updates, while Git stays the source of truth.
          </p>
          <p className="mt-3 text-sm text-muted/80">
            MkDocs is the SSOT for documentation. This page is a short summary for kanb.us.
          </p>
        </div>

        <div className="mt-6">
          <a
            href="/features/realtime-collaboration"
            className="inline-flex items-center gap-2 text-sm text-muted hover:text-foreground transition-colors"
          >
            <span>←</span>
            <span>Back to Realtime Collaboration feature page</span>
          </a>
        </div>

        <div className="bg-background rounded-xl border border-border overflow-hidden">
          <img
            src="/images/realtime-collaboration-diagram.svg"
            alt="Realtime Collaboration architecture diagram"
            className="w-full h-auto block"
          />
        </div>

        <div className="prose prose-slate max-w-none text-muted leading-relaxed space-y-6">
          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Quickstart (Local UDS)
          </h2>
          <CodeBlock label="Terminal">
{`# Terminal 1: start local broker
kbs gossip broker

# Terminal 2: watch + update overlay
kbs gossip watch`}
          </CodeBlock>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Quickstart (Local MQTT)
          </h2>
          <CodeBlock label="Terminal">
{`kbs gossip watch --transport mqtt --broker auto`}
          </CodeBlock>
          <p className="text-sm text-muted/80">
            If Mosquitto is installed and no broker is reachable, Kanbus can autostart a local broker and write
            <code>~/.kanbus/run/broker.json</code>.
          </p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Config
          </h2>
          <CodeBlock label=".kanbus.yml">
{`realtime:
  transport: auto            # auto | uds | mqtt
  broker: auto               # auto | off | mqtt://... | mqtts://...
  autostart: true            # autostart mosquitto if unreachable (MQTT only)
  keepalive: false           # keep autostarted broker running
  uds_socket_path: null      # override UDS socket path
  topics:
    project_events: "projects/{project}/events"

overlay:
  enabled: true
  ttl_s: 86400`}
          </CodeBlock>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Canonical Docs
          </h2>
          <p>
            For envelope schema, dedupe rules, overlay merge semantics, GC + hooks, and troubleshooting, use the canonical MkDocs page.
          </p>
          <p>
            <a href={docsHref} className="text-selected font-semibold hover:underline">
              {docsLabel}
            </a>
          </p>
          {!canonicalDocs ? (
            <p className="text-xs text-muted/70">
              Tip: set <code>GATSBY_MKDOCS_BASE_URL</code> in the kanb.us build to link to a deployed MkDocs site.
            </p>
          ) : null}
        </div>
      </div>
    </DocsLayout>
  );
};

export default DocsRealtimeCollaborationPage;

