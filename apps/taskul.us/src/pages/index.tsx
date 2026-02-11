import * as React from "react";
import { Layout, Section, Hero } from "../components";

const IndexPage = () => {
  return (
    <Layout>
      <Hero
        title="Git-backed project management"
        subtitle="Files are the database. Taskulus keeps your issues, plans, and code in one repository."
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
                JSON Issues
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Every issue is a single JSON file. Branch, merge, and review
                issues just like code.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm hover:shadow-md transition-shadow">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                No Merge Conflicts
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Designed with a minimum-schema format that avoids conflicts even
                on active teams.
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
                Live Data
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Use Jinja2 templates to pull live issue counts, status, and
                lists into your planning docs.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Versioned Plans
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Your specifications evolve with your code. Go back in time and
                see exactly what was planned.
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
                Easy to install, easy to extend. Perfect for scripting and local
                workflows.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm hover:shadow-md transition-shadow">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Rust
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                High-performance backend for CI/CD pipelines and large
                repositories.
              </p>
            </div>
          </div>
        </Section>

        <Section
          title="Why Taskulus?"
          subtitle="Built for developers who want to own their data."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-3">
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Vs. Beads
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Taskulus is a spiritual successor to Beads, focusing on
                simplicity and removing complex graph requirements.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Vs. Jira
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                No slow web UI. No separate login. No downtime. Your data is
                always on your disk.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Vs. Markdown
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Structured data where you need it (status, priority), free text
                where you want it (description).
              </p>
            </div>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default IndexPage;
