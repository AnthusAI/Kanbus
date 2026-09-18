import * as React from "react";
import { Layout, Section, Hero, CodeBlock } from "../../components";
import { FeaturePictogram } from "../../components/FeaturePictogram";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const designHref = "https://github.com/AnthusAI/Kanbus/blob/develop/docs/ISSUE_ROUTER_DESIGN.md";
const operatorHref = "https://github.com/AnthusAI/Kanbus/blob/develop/docs/ISSUE_ROUTER_OPERATOR_GUIDE.md";

const IssueRouterPage = () => {
  return (
    <Layout>
      <Hero
        eyebrow="ISSUE ROUTER"
        title="Put bounded agent work on a reviewable path."
        subtitle="The Kanbus Issue Router turns an eligible, labeled issue into one controlled Codex run—then returns the result as a pull request and an In Review item. Your team stays in charge of what starts, what ships, and what gets merged."
        actions={
          <>
            <a href="#start" className="cta-button px-6 py-3 text-sm transition-all hover:brightness-95">
              See the workflow
            </a>
            <a href={operatorHref} className="text-sm font-semibold text-foreground hover:text-selected transition-colors">
              Operator guide →
            </a>
          </>
        }
        rightPane={
          <figure className="w-full overflow-hidden rounded-2xl border border-border bg-card shadow-2xl shadow-blue-950/25">
            <FeaturePictogram
              type="issue-router"
              className="min-h-[240px]"
              style={{ minHeight: 240 }}
            />
          </figure>
        }
      />

      <div id="start" className="space-y-0">
        <Section
          title="The question"
          subtitle="Can we let an agent do real work without turning the board into an opaque automation queue?"
          variant="alt"
        >
          <Card className="p-8 md:p-10">
            <CardContent className="p-0 max-w-4xl space-y-5 text-lg leading-relaxed text-muted">
              <p>
                Yes. The Issue Router is an optional Kanbus reconciliation loop that starts only work your workflow has made eligible. It gives the agent a bounded package and an isolated Git worktree, validates a structured result, and opens or updates a GitHub pull request. A completed run goes to your configured review state; it does not close the issue or merge the PR.
              </p>
              <p>
                Kanbus remains Git-native throughout. Issue data, event history, checkpoints, and router-owned status changes are durable and inspectable. The model is an executor inside a deterministic workflow—not the system that decides what work exists or whether it is accepted.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="What changes for a team"
          subtitle="A small routing label is the opt-in. Everything else stays familiar."
        >
          <div className="grid gap-6 md:grid-cols-3">
            <Card className="p-7">
              <CardHeader className="p-0 mb-4">
                <span className="font-mono text-sm text-selected">01 — SELECT</span>
                <h3 className="mt-2 text-xl font-bold text-foreground">Mark the package</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Add one <code>agent-class:…</code> or <code>agent-provider:…</code> label to an issue. Its untagged descendants travel with it as one bounded package.
              </CardContent>
            </Card>
            <Card className="p-7">
              <CardHeader className="p-0 mb-4">
                <span className="font-mono text-sm text-selected">02 — DISPATCH</span>
                <h3 className="mt-2 text-xl font-bold text-foreground">Run with guardrails</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                The router respects policy, dependencies, configured capacity, routing order, and coordination before it gives one eligible package to Codex.
              </CardContent>
            </Card>
            <Card className="p-7">
              <CardHeader className="p-0 mb-4">
                <span className="font-mono text-sm text-selected">03 — REVIEW</span>
                <h3 className="mt-2 text-xl font-bold text-foreground">Review ordinary Git work</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                A valid completed result produces or updates a pull request and places the package in Review. Your normal review and merge practices remain the final gate.
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="How a run works"
          subtitle="A deliberate sequence that preserves the project’s source of truth."
          variant="alt"
        >
          <div className="grid gap-6 lg:grid-cols-[1.15fr_.85fr]">
            <Card className="p-8">
              <CardContent className="p-0">
                <ol className="space-y-6">
                  {[
                    ["Plan", "The router reads the configured pending state and produces a deterministic list of eligible and deferred packages."],
                    ["Claim", "It records a claim with a unique ID and revision, using the project’s configured coordination level."],
                    ["Execute", "Codex works in a run-specific Git worktree and returns one structured result rather than directly changing Kanbus issue data."],
                    ["Validate", "Kanbus verifies package scope, workflow transitions, claim ownership, checkpoints, and result shape before accepting anything."],
                    ["Publish", "Accepted work updates the dedicated router-state Git branch, creates or updates the pull request, and moves the package to Review."],
                  ].map(([title, text], index) => (
                    <li key={title} className="flex gap-4">
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-selected/10 font-mono text-sm font-bold text-selected">{index + 1}</span>
                      <div>
                        <h3 className="font-bold text-foreground">{title}</h3>
                        <p className="mt-1 text-muted leading-relaxed">{text}</p>
                      </div>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-5">
                <h3 className="text-xl font-bold text-foreground">The safe default</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>One call processes at most one eligible package. Start by looking at the plan; then dispatch deliberately.</p>
                <CodeBlock label="Terminal">{`kanbus router plan
kanbus router run --once`}</CodeBlock>
                <p className="text-sm">For continuous operation, watch mode reconciles immediately and on the configured interval. It also polls GitHub pull-request state for work already in review.</p>
                <CodeBlock label="Terminal">{`kanbus router run --watch`}</CodeBlock>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Progressive coordination"
          subtitle="Start simple. Add coordination only when the number of workers demands it."
        >
          <div className="grid gap-6 md:grid-cols-3">
            <Card className="p-7 border-selected/30">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">One worker: Git</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-3 text-muted leading-relaxed">
                <p>For a single worker, Git-backed state is enough. The router’s watch loop polls the shared router-state branch at its bounded interval.</p>
                <p className="text-sm">No MQTT or mutex service is required to begin.</p>
              </CardContent>
            </Card>
            <Card className="p-7">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Faster visibility: MQTT + Git</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-3 text-muted leading-relaxed">
                <p>MQTT can wake routers sooner when another worker publishes an update. Git remains the durable record and polling fallback.</p>
                <p className="text-sm">This is soft coordination: duplicate starts remain possible during a visibility gap.</p>
              </CardContent>
            </Card>
            <Card className="p-7">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Hard exclusion: Mutex API</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-3 text-muted leading-relaxed">
                <p>Put the Mutex API first when workers must not concurrently start the same package. A live lease is then required before an adapter starts.</p>
                <p className="text-sm">If the mutex service is unavailable, the router fails closed instead of silently weakening coordination.</p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="What the router will not do"
          subtitle="Clear boundaries make automated work easier to trust and easier to operate."
          variant="alt"
        >
          <div className="grid gap-6 md:grid-cols-2">
            <Card className="p-8">
              <CardHeader className="p-0 mb-4"><h3 className="text-xl font-bold text-foreground">It does not replace human review</h3></CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">The router opens or updates a pull request and moves a package to Review. It never merges a pull request, and it never treats model completion as approval.</CardContent>
            </Card>
            <Card className="p-8">
              <CardHeader className="p-0 mb-4"><h3 className="text-xl font-bold text-foreground">It does not let an agent rewrite the board</h3></CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">The adapter proposes a structured result. Kanbus validates scope and legal state transitions, then records accepted changes through its own event history.</CardContent>
            </Card>
            <Card className="p-8">
              <CardHeader className="p-0 mb-4"><h3 className="text-xl font-bold text-foreground">It does not require a cloud queue</h3></CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">Issues remain ordinary project files in Git. Shared router state lives on a dedicated Git branch; MQTT and the mutex layer are optional coordination upgrades.</CardContent>
            </Card>
            <Card className="p-8">
              <CardHeader className="p-0 mb-4"><h3 className="text-xl font-bold text-foreground">It does not hide failure</h3></CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">Retryable failures use bounded backoff. A blocked result is visible as blocked work. Stale or losing claims cannot publish accepted status, checkpoint, or PR updates.</CardContent>
            </Card>
          </div>
        </Section>

        <Section title="Questions teams ask" subtitle="The operational answers, without hand-waving.">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card className="p-8"><CardHeader className="p-0 mb-3"><h3 className="text-lg font-bold text-foreground">Can I choose which work is routed?</h3></CardHeader><CardContent className="p-0 text-muted leading-relaxed">Yes. Only issues with exactly one route label opt in. Everything else stays on the normal board workflow.</CardContent></Card>
            <Card className="p-8"><CardHeader className="p-0 mb-3"><h3 className="text-lg font-bold text-foreground">Can I cap agent activity?</h3></CardHeader><CardContent className="p-0 text-muted leading-relaxed">Yes. Project, review, agent-class, and provider-profile WIP limits are checked before a package can start.</CardContent></Card>
            <Card className="p-8"><CardHeader className="p-0 mb-3"><h3 className="text-lg font-bold text-foreground">What happens when a PR needs changes?</h3></CardHeader><CardContent className="p-0 text-muted leading-relaxed">The package returns from Review to the configured active state, ahead of new pending work, so the next run can continue the same pull request.</CardContent></Card>
            <Card className="p-8"><CardHeader className="p-0 mb-3"><h3 className="text-lg font-bold text-foreground">What happens if a worker dies?</h3></CardHeader><CardContent className="p-0 text-muted leading-relaxed">After the execution lease becomes stale, a later worker can take over using a newer claim revision and the latest accepted checkpoint.</CardContent></Card>
          </div>
        </Section>

        <Section title="Ready to operate it?" subtitle="Configure one route, inspect the plan, and keep the normal pull-request review loop intact." variant="alt">
          <Card className="p-8 md:p-10 text-center">
            <CardContent className="p-0 space-y-6">
              <p className="mx-auto max-w-2xl text-lg leading-relaxed text-muted">Read the operator guide for the configuration contract and the design document for exact routing, fencing, retry, and lifecycle semantics.</p>
              <div className="flex flex-col items-center justify-center gap-4 sm:flex-row">
                <a href={operatorHref} className="cta-button px-6 py-3 text-sm transition-all hover:brightness-95">Read the operator guide →</a>
                <a href={designHref} className="text-sm font-semibold text-foreground hover:text-selected transition-colors">Read the design contract →</a>
              </div>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default IssueRouterPage;

export const Head = () => (
  <>
    <title>Issue Router — Kanbus</title>
    <meta
      name="description"
      content="Dispatch explicitly labeled Kanbus issue packages through Codex with Git-backed state, progressive coordination, and a pull-request review gate."
    />
  </>
);
