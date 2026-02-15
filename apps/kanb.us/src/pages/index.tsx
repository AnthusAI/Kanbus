import * as React from "react";
import { Layout, Section, Hero } from "../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const IndexPage = () => {
  return (
    <Layout>
      <Hero
        title="A tiny Jira clone for your repo"
        subtitle="Files are the database. Kanbus keeps your issues, plans, and code in one repository, without the complexity."
        eyebrow="Kanbus"
        actions={
          <>
            <a
              href="/docs"
              className="rounded-full bg-selected px-6 py-3 text-sm font-semibold text-background shadow-card hover:brightness-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-selected transition-all"
            >
              Get Started
            </a>
            <a
              href="/philosophy"
              className="text-sm font-semibold leading-6 text-foreground hover:text-selected transition-all"
            >
              Learn More <span aria-hidden="true">→</span>
            </a>
          </>
        }
      />

      <div className="space-y-12">
        <Section
          title="Files are the database"
          subtitle="Stop syncing your work to a separate silo. Kanbus stores everything in your Git repository."
        >
          <div className="grid gap-8 md:grid-cols-2">
            <Card className="p-8 shadow-card hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">One File Per Issue</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Other systems store everything in one big JSONL file, causing constant merge conflicts.
                Kanbus creates a separate JSON file for each issue, so your team (and agents) can work
                in parallel without blocking each other.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">No Friction</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Git hooks should help you, not block you. There is no database server to maintain,
                no background process to crash, and no complex synchronization logic. Each command scans
                the project files directly.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Collision-Free IDs</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Kanbus assigns hash-based unique IDs to avoid collisions during concurrent edits.
                Unlike hierarchical numbering schemes, hash IDs work safely when multiple agents
                create child issues in parallel.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Shared Datastore Support</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Multiple projects can point to a shared data store while keeping project_key per issue
                to prevent collisions. Track work across codebases with centralized visibility and
                per-project namespacing.
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Integrated Wiki"
          subtitle="The forest vs the trees. Live planning documents that render real-time issue data."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-2">
            <Card className="p-8 shadow-card bg-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">
                  Live Context for Agents
                </h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Use Jinja2 templates to inject live lists of open tasks directly into your planning docs.
                Agents can read these docs to get up to speed instantly on any initiative.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card bg-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Full Graph Support</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Define dependencies, blockers, and relationships between issues. We support a rich graph
                of associations without the overhead of a graph database.
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Dual Implementation"
          subtitle="One behavior specification driving two complete implementations."
        >
          <div className="grid gap-8 md:grid-cols-2">
            <Card className="p-8 shadow-card hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Python</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Easy to install via pip. Perfect for scripting, local workflows, and integrating with AI tools.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card hover:-translate-y-1 transition-transform">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Rust</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                High-performance binary for CI/CD pipelines and large repositories. 100% behavior parity with
                the Python version.
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Why Kanbus?"
          subtitle="Built for the age of AI-assisted development."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-3">
            <Card className="p-8 shadow-card bg-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Successor to Beads</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Inspired by the elegant Beads cognitive framework, but re-engineered for Git. We removed the
                SQLite database, used separate files to eliminate merge conflicts, and adopted standard Jira
                terms to better leverage AI pre-training.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card bg-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Vs. Jira</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Your data is local. No web latency, no login screens, and native CLI access for your AI agents
                to read and write tasks. And there are no per-seat costs—it's just your repo.
              </CardContent>
            </Card>
            <Card className="p-8 shadow-card bg-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Vs. Markdown</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                You get structured data (priority, status) where you need it, and free-form Markdown descriptions
                where you want it.
              </CardContent>
            </Card>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default IndexPage;
