import * as React from "react";
import { Layout, Section, Hero } from "../components";

const PhilosophyPage = () => {
  return (
    <Layout>
      <Hero
        title="Design Philosophy"
        subtitle="Taskulus is built on a set of core principles that prioritize developer experience, transparency, and longevity."
        eyebrow="System Design"
      />

      <div className="space-y-12">
        <Section
          title="Core Principles"
          subtitle="The fundamental rules that guide the development of the Taskulus system."
        >
          <div className="grid gap-8 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm hover:shadow-md transition-shadow">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                1. Files are the database
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                There is no hidden SQLite file or remote API. The state of your
                project is strictly defined by the JSON files in your repository.
                If you delete a file, the issue is gone.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm hover:shadow-md transition-shadow">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                2. Human-readable by default
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                You should be able to read and understand your project data
                without the Taskulus CLI. JSON is used for data, Markdown for
                content. IDs are short and memorable.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm hover:shadow-md transition-shadow">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                3. Minimal schema
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                We enforce only what is necessary for the graph to work.
                Everything else is extensible. We don't presume to know your
                workflow.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm hover:shadow-md transition-shadow">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                4. Two implementations, one spec
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                We build in Python for scripting and Rust for performance. Both
                are driven by a single, shared Gherkin behavior specification.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm hover:shadow-md transition-shadow">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                5. The spec is the artifact
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                The behavior specification IS the product definition. Code exists
                only to satisfy the spec.
              </p>
            </div>
          </div>
        </Section>

        <Section
          title="Architecture"
          subtitle="How Taskulus works under the hood."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                In-Memory Index
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Taskulus does not run a background daemon. When you run a command,
                it scans your project files, builds an in-memory graph, performs
                the operation, and exits.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                The Wiki Engine
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                The `wiki` command renders Markdown templates using the Jinja2
                engine. It injects a `project` context object that gives you
                access to the entire issue graph.
              </p>
            </div>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default PhilosophyPage;
