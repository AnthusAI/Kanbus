import * as React from "react";
import { Layout, Section, Hero, FullVideoPlayer, FeaturePictogram, CodeBlock } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { getVideoById } from "../../content/videos";
import { getVideoSrc } from "../../lib/getVideoSrc";
import { getGitHubDocsSourceUrl, getMkDocsDocUrl } from "../../lib/getMkDocsSrc";

const RealtimeCollaborationPage = () => {
  const featureVideo = getVideoById("realtime-collaboration");
  const videoPoster = featureVideo?.poster ? getVideoSrc(featureVideo.poster) : undefined;
  const videoSrc = featureVideo ? getVideoSrc(featureVideo.filename) : "";

  const canonicalDocs = getMkDocsDocUrl("REALTIME");
  const sourceDocs = getGitHubDocsSourceUrl("docs/REALTIME.md");
  const docsHref = canonicalDocs ?? sourceDocs;
  const docsLabel = canonicalDocs ? "Read canonical docs →" : "Read docs (source) →";

  return (
    <Layout>
      <Hero
        eyebrow="New Feature"
        title="Realtime Collaboration"
        subtitle="Federated realtime updates for agents and humans. Gossip messaging for instant visibility, with an overlay cache for speculative reads between pulls."
        rightPane={<FeaturePictogram type="realtime-collaboration" />}
        bottomPane={
          <div className="w-full flex flex-col items-center justify-center mt-12 mb-8 gap-12">
            {videoSrc ? (
              <FullVideoPlayer src={videoSrc} poster={videoPoster} videoId="realtime-collaboration" />
            ) : null}
          </div>
        }
      />

      <div className="space-y-12">
        <Section title="Architecture" subtitle="Realtime is additive: gossip adds visibility without changing your Git workflow.">
          <Card className="p-8">
            <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
              <p>
                Every change still writes to your working tree first: issue JSON plus an append-only event file. Realtime collaboration
                adds a pub/sub notification channel and a disposable overlay cache so other tools can react immediately before a pull
                lands.
              </p>
              <div className="bg-background rounded-xl border border-border overflow-hidden">
                <img
                  src="/images/realtime-collaboration-diagram.svg"
                  alt="Realtime Collaboration architecture diagram"
                  className="w-full h-auto block"
                />
              </div>
              <p className="text-sm text-muted/80">
                The overlay never resolves conflicts. Git remains the only conflict mechanism.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section title="What You Get" subtitle="Instant awareness without changing your Git workflow." variant="alt">
          <div className="grid gap-6 md:grid-cols-2">
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Immediate visibility</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Watchers learn about changes immediately, without waiting for a <code>git pull</code>. This is notification, not
                  dispatch.
                </p>
              </CardContent>
            </Card>
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Speculative reads</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  The overlay cache can temporarily override reads so the UI can show updates learned via gossip before Git history
                  catches up.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section title="Gossip Layer" subtitle="Small pub/sub messages with deterministic semantics.">
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Best-effort publishing</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Mutations never depend on the broker. A command can succeed even if publishing fails. Receivers dedupe notifications and
                ignore self-produced messages.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section title="Overlay Cache" subtitle="Disposable snapshots and tombstones that never change Git’s role." variant="alt">
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Merge rule: base + overlay</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Watchers write issue snapshots to <code>project/.overlay/issues/</code>. Deletes are explicit tombstones in
                <code>project/.overlay/tombstones/</code>. Reads merge Git-backed base with overlay when the overlay is newer.
              </p>
              <p>Overlay entries are self-pruning and safe to delete wholesale.</p>
            </CardContent>
          </Card>
        </Section>

        <Section title="Transports" subtitle="UDS locally, MQTT for LAN and cloud.">
          <div className="grid gap-6 md:grid-cols-2">
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">UDS (local)</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Run a lightweight local broker on a Unix domain socket for same-machine collaboration between tools.
                </p>
                <CodeBlock label="Terminal">
{`kbs gossip broker
kbs gossip watch`}
                </CodeBlock>
              </CardContent>
            </Card>
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">MQTT (LAN / cloud)</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Use Mosquitto locally or a managed MQTT broker later. Kanbus can autostart a local Mosquitto when configured.
                </p>
                <CodeBlock label="Terminal">
{`kbs gossip watch --transport mqtt --broker auto`}
                </CodeBlock>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section title="What It Is Not" subtitle="Realtime coordination without changing the conflict model." variant="alt">
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <ul className="list-disc pl-5 space-y-2">
                <li>No automatic commit, push, or pull.</li>
                <li>No gossip authority: your repository files are always the truth.</li>
                <li>No conflict resolution beyond Git conflicts.</li>
                <li>No exclusive task claiming (dispatch belongs elsewhere).</li>
              </ul>
            </CardContent>
          </Card>
        </Section>

        <Section title="Learn More" subtitle="Quickstart and full technical details.">
          <Card className="p-8">
            <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
              <CodeBlock label="Quickstart">
{`# Terminal 1 (UDS broker)
kbs gossip broker

# Terminal 2 (watch + overlay)
kbs gossip watch`}
              </CodeBlock>
              <div className="flex flex-col sm:flex-row gap-4 sm:items-center sm:justify-center">
                <a
                  href="/docs/features/realtime-collaboration"
                  className="cta-button px-6 py-3 text-sm transition-all hover:brightness-95 text-center"
                >
                  Read the summary →
                </a>
                <a
                  href={docsHref}
                  className="text-sm font-semibold leading-6 text-foreground hover:text-selected transition-all text-center"
                >
                  {docsLabel}
                </a>
              </div>
              {!canonicalDocs ? (
                <p className="text-xs text-muted/70 text-center">
                  Tip: set <code>GATSBY_MKDOCS_BASE_URL</code> to link to your deployed MkDocs site.
                </p>
              ) : null}
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default RealtimeCollaborationPage;
