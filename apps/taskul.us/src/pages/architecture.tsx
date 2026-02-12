import * as React from "react";
import { Layout, Section, Hero } from "../components";

const ArchitecturePage = () => {
  return (
    <Layout>
      <Hero
        title="Architecture"
        subtitle="Taskulus treats Gherkin as high-level source code and treats implementation code as generated artifacts."
        eyebrow="System Design"
      />

      <div className="space-y-12">
        <Section
          title="Spec-Driven Design"
          subtitle="Gherkin features are treated as high-level source code."
        >
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
            <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-4">
              Gherkin as Source Code
            </h3>
            <div className="space-y-4 text-slate-600 dark:text-slate-400 leading-relaxed">
              <p>
                Taskulus treats its Gherkin features as high-level source code.
                The specifications are authoritative, and implementations are
                generated artifacts that must conform to them.
              </p>
              <p>
                This is an extreme form of behavior-driven design: the Gherkin
                code is not derived from the implementation, it defines it.
              </p>
            </div>
          </div>
        </Section>

        <Section
          title="Single Source of Truth"
          subtitle="A shared features directory keeps behavior in lockstep."
          variant="alt"
        >
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
            <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-4">
              One Shared Features Folder
            </h3>
            <div className="space-y-4 text-slate-600 dark:text-slate-400 leading-relaxed">
              <p>
                Taskulus maintains a single <code>features/</code> directory for
                behavior specifications. Both the Python and Rust implementations
                consume the exact same feature files.
              </p>
              <p>
                This keeps parity at the specification level and prevents behavior
                drift between languages.
              </p>
            </div>
          </div>
        </Section>

        <Section
          title="Multi-Target Implementations"
          subtitle="Multiple languages, identical behavior."
        >
          <div className="grid gap-8 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Python
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                The Python implementation is designed for fast iteration and
                agent integration while remaining fully constrained by the shared
                behavior specifications.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Rust
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                The Rust implementation targets performance and reliability while
                staying behaviorally identical to the Python build through the same
                Gherkin specs.
              </p>
            </div>
          </div>
        </Section>

        <Section
          title="Operational Implications"
          subtitle="How spec-driven design shapes development."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-2">
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Feature Work Starts With Gherkin
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Every behavior change begins with a specification update. Code exists
                to satisfy specs, not the other way around.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm">
              <h3 className="text-xl font-bold text-slate-900 dark:text-white mb-3">
                Parity Is Non-Negotiable
              </h3>
              <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
                Shared specifications plus parity checks ensure behavior remains
                identical across implementations.
              </p>
            </div>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default ArchitecturePage;
