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
          title="Why Taskulus Exists"
          subtitle="Game-changing technology for the age of AI agents."
        >
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
            <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-4">
              The Sleep Factor
            </h3>
            <div className="space-y-4 text-slate-600 dark:text-slate-400 leading-relaxed">
              <p>
                The motivation for Taskulus came from a simple need: to offload
                mental context. When you are juggling dozens of open loops—chat
                sessions, pending tasks, architectural decisions—you need a place
                to put them that doesn't require "logging in" or managing infrastructure.
              </p>
              <p>
                Taskulus allows you (and your AI agents) to dump context immediately
                into the repository. It's the difference between keeping 15 plates
                spinning in your head and putting them on a shelf.
              </p>
            </div>
          </div>
        </Section>

        <Section
          title="Inspiration & Lineage"
          subtitle="Standing on the shoulders of giants."
          variant="alt"
        >
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
            <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-4">
              A Spiritual Successor to Beads
            </h3>
            <div className="space-y-4 text-slate-600 dark:text-slate-400 leading-relaxed">
              <p>
                This project was inspired by <a href="https://github.com/steveyegge/beads" className="text-primary-600 hover:underline">Beads</a> and is intended as a spiritual successor that embraces the elegant domain-specific cognitive framework it pioneered. We are deeply grateful to the Beads author and community for proving the concept so well.
              </p>
              <p>
                Taskulus represents the next generation of this idea, improved for the era of AI agents:
              </p>
              <ul className="list-disc list-inside space-y-2 ml-4">
                <li>
                  <strong>Thinner layer over Git:</strong> We removed the secondary SQLite database to eliminate synchronization complexity.
                </li>
                <li>
                  <strong>Git-aligned storage:</strong> Separate files for separate tasks mean no merge conflicts when agents work in parallel.
                </li>
                <li>
                  <strong>Focused Cognitive Model:</strong> We stripped away 100+ unused attributes to focus on the core cognitive framework, reducing context pollution for AI models.
                </li>
                <li>
                  <strong>Standard Nomenclature:</strong> We use standard terms (Epics, Tasks) to leverage the massive pre-training AI models already have on these concepts.
                </li>
              </ul>
            </div>
          </div>
        </Section>

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
                There is no hidden SQLite file, no background daemon, and no remote API.
                The state of your project is strictly defined by the JSON files in your
                repository. Each command scans those files directly—the files are the truth.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm hover:shadow-md transition-shadow">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                2. One File Per Issue
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Other systems store everything in a single JSONL file. This guarantees
                merge conflicts when two people (or agents) work on different tasks
                simultaneously. Taskulus splits every issue into its own file,
                letting Git handle the merging naturally.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm hover:shadow-md transition-shadow">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                3. Minimal, Extensible Schema
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                We don't need 130 attributes to track a task. We need a status,
                a priority, and relationships. Taskulus enforces a minimal graph schema
                to ensure things work, and leaves the rest to you.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm hover:shadow-md transition-shadow">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                4. Agent-Native
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Taskulus is basically Jira + Confluence for agents. The CLI allows
                agents to read the current state of the world, and the Wiki engine
                allows them to read dynamic summaries of initiatives. It is designed
                to be the memory bank for your AI workforce.
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
                No Complexity
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                We strictly avoid features that introduce synchronization issues,
                like "atomic checkouts" or locking. We treat Git as the database
                and respect its eventual consistency model. This keeps the tool
                extremely simple and reliable.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                The Wiki Engine
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                The `wiki` command renders Markdown templates using the Jinja2
                engine. It injects a `project` context object that gives you
                access to the entire issue graph. This allows you to write
                "living documents" that always reflect the latest status.
              </p>
            </div>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default PhilosophyPage;
