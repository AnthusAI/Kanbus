import * as React from "react";
import { Layout, Section, Hero, CodeBlock } from "../components";

const GettingStartedPage = () => {
  return (
    <Layout>
      <Hero
        title="Getting Started"
        subtitle="Install the CLI and start managing work with Kanbus in minutes."
        eyebrow="Quick Start"
      />

      <div className="space-y-12">
        <Section
          title="Download the kanbusr binary"
          subtitle="Grab the prebuilt Rust CLI for your platform."
        >
          <div className="space-y-6">
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
              Download the latest release from GitHub Releases. Replace the
              version and target with the artifact that matches your platform.
            </p>
            <CodeBlock label="Example (Linux x86_64)">
              {`curl -L -o kanbusr.tar.gz https://github.com/AnthusAI/Kanbus/releases/download/v0.1.0/kanbusr-x86_64-unknown-linux-gnu.tar.gz
tar -xzf kanbusr.tar.gz
chmod +x kanbusr
./kanbusr --help`}
            </CodeBlock>
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
              The binary name is <code>kanbusr</code>.
            </p>
          </div>
        </Section>

        <Section
          title="Install with pip"
          subtitle="Use the Python CLI for fast iteration and scripting."
          variant="alt"
        >
          <div className="space-y-6">
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
              Install Kanbus from PyPI and use the <code>kanbus</code> command.
            </p>
            <CodeBlock label="Python">
              {`python -m pip install kanbus
kanbus --help`}
            </CodeBlock>
          </div>
        </Section>

        <Section
          title="Install with cargo"
          subtitle="Rust installation is coming soon."
        >
          <div className="space-y-6">
            <div className="inline-flex items-center rounded-full border border-slate-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-1 text-xs font-semibold text-slate-600 dark:text-slate-300">
              Coming soon
            </div>
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
              We will publish <code>kanbusr</code> to crates.io once the registry
              listing is ready.
            </p>
            <CodeBlock label="Cargo (coming soon)">
              {`cargo install kanbusr`}
            </CodeBlock>
          </div>
        </Section>

        <Section
          title="Build from source"
          subtitle="Clone the repo and run directly."
          variant="alt"
        >
          <div className="space-y-6">
            <CodeBlock label="Clone">
              {`git clone https://github.com/AnthusAI/Kanbus.git
cd Kanbus`}
            </CodeBlock>
            <CodeBlock label="Rust CLI">
              {`cd rust
cargo build --release
./target/release/kanbusr --help`}
            </CodeBlock>
            <CodeBlock label="Python CLI">
              {`cd python
python -m pip install -e .
kanbus --help`}
            </CodeBlock>
          </div>
        </Section>

        <Section
          title="Initialize Your Repository"
          subtitle="Create the Kanbus structure in an existing git repo."
        >
          <div className="space-y-6">
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
              Run <code>kanbus init</code> once in the repository root. It creates
              the <code>project/</code> directory and the repo-level
              <code>.kanbus.yml</code> file.
            </p>
            <CodeBlock label="Initialize">
              {`cd your-repo
git init
kanbus init`}
            </CodeBlock>
          </div>
        </Section>

        <Section
          title="Keep Configuration Updated"
          subtitle="Evolve workflows and defaults without re-running init."
          variant="alt"
        >
          <div className="space-y-6">
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
              Edit <code>project/config.yaml</code> to change hierarchy,
              workflows, priorities, and defaults. Use
              <code>.kanbus.override.yml</code> for local-only settings like
              assignee or time zone.
            </p>
            <CodeBlock label="Validate">
              {`kanbus list
kanbus ready`}
            </CodeBlock>
          </div>
        </Section>

        <Section
          title="Beads Compatibility During Transition"
          subtitle="Keep JSONL data while moving to Kanbus."
        >
          <div className="space-y-6">
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
              If your repo still stores issues in <code>.beads/issues.jsonl</code>,
              enable compatibility in both config files.
            </p>
            <CodeBlock label="Compatibility">
              {`.kanbus.yml
beads_compatibility: true

project/config.yaml
beads_compatibility: true`}
            </CodeBlock>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default GettingStartedPage;
