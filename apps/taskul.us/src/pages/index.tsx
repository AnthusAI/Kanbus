import * as React from "react";
import { Layout, Section, Hero } from "../components";

const IndexPage = () => {
  return (
    <Layout>
      <Hero
        title="A tiny Jira clone for your repo"
        subtitle="Files are the database. Taskulus keeps your issues, plans, and code in one repository, without the complexity."
        eyebrow="Taskulus"
        actions={
          <>
            <a
              href="/docs"
              className="rounded-full bg-primary-600 px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-primary-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 transition-all"
            >
              Get Started
            </a>
            <a
              href="/philosophy"
              className="text-sm font-semibold leading-6 text-slate-900 dark:text-white hover:text-primary-600 dark:hover:text-primary-400 transition-all"
            >
              Learn More <span aria-hidden="true">→</span>
            </a>
          </>
        }
      />

      <div className="space-y-12">
        <Section
          title="Files are the database"
          subtitle="Stop syncing your work to a separate silo. Taskulus stores everything in your Git repository."
        >
          <div className="grid gap-8 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm hover:shadow-md transition-shadow">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                One File Per Issue
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Other systems store everything in one big JSONL file, causing
                constant merge conflicts. Taskulus creates a separate JSON file
                for each issue, so your team (and agents) can work in parallel
                without blocking each other.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm hover:shadow-md transition-shadow">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                No Daemons, No SQL
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                There is no database server to maintain, no background process to
                crash, and no complex synchronization logic. We build a fast
                in-memory index from your files on the fly.
              </p>
            </div>
          </div>
        </Section>

        <Section
          title="Integrated Wiki"
          subtitle="The forest vs the trees. Live planning documents that render real-time issue data."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Live Context for Agents
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Use Jinja2 templates to inject live lists of open tasks directly
                into your planning docs. Agents can read these docs to get up to
                speed instantly on any initiative.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Full Graph Support
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Define dependencies, blockers, and relationships between issues.
                We support a rich graph of associations without the overhead of a
                graph database.
              </p>
            </div>
          </div>
        </Section>

        <Section
          title="Dual Implementation"
          subtitle="One behavior specification driving two complete implementations."
        >
          <div className="grid gap-8 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm hover:shadow-md transition-shadow">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Python
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Easy to install via pip. Perfect for scripting, local
                workflows, and integrating with AI tools.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm hover:shadow-md transition-shadow">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Rust
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                High-performance binary for CI/CD pipelines and large
                repositories. 100% behavior parity with the Python version.
              </p>
            </div>
          </div>
        </Section>

        <Section
          title="Why Taskulus?"
          subtitle="Built for the age of AI-assisted development."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-3">
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Vs. Beads
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                We fixed the concurrency problem by splitting issues into separate
                files, and removed the heavy graph validation overhead.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Vs. Jira
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Your data is local. No web latency, no login screens, and native
                CLI access for your AI agents to read and write tasks.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Vs. Markdown
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                You get structured data (priority, status) where you need it,
                and free-form Markdown descriptions where you want it.
              </p>
            </div>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default IndexPage;
