import * as React from "react";
import { Layout, Section, Hero } from "../components";

const RoadmapPage = () => {
  return (
    <Layout>
      <Hero
        title="Roadmap"
        subtitle="The path to version 1.0. We are building Taskulus in public, phase by phase."
        eyebrow="Development Plan"
      />

      <div className="space-y-12">
        <Section
          title="Phase 1: Foundation"
          subtitle="Establishing the core data model and CLI interactions."
        >
          <div className="grid gap-8 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Repository Setup
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Monorepo structure with Python and Rust workspaces sharing
                Gherkin specifications.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Data Model
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                JSON schema for Issues, Tasks, and Comments. File I/O
                operations.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                In-Memory Index
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Graph construction from file scan. ID generation and validation.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                CLI Workflow
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Basic commands: `init`, `create`, `list`, `show`, `update`,
                `delete`.
              </p>
            </div>
          </div>
        </Section>

        <Section
          title="Phase 2: The Wiki Engine"
          subtitle="Connecting the code to the planning documents."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Rendering Engine
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Jinja2 integration for processing Markdown templates.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Template Context
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Exposing the issue graph (counts, status, lists) to the template
                context.
              </p>
            </div>
          </div>
        </Section>

        <Section
          title="Phase 3: Polish & Release"
          subtitle="Refining the experience for daily use."
        >
          <div className="grid gap-8 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Search
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Full-text search across issues and comments.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Validation
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Strict schema validation and graph integrity checks (orphaned
                dependencies).
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Statistics
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Burndown charts and velocity metrics generated from history.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                IDE Integration
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                VS Code extension for highlighting and auto-complete.
              </p>
            </div>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default RoadmapPage;
