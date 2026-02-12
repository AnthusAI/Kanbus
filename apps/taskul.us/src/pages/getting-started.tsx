import * as React from "react";
import { Layout, Section, Hero, CodeBlock } from "../components";

const GettingStartedPage = () => {
  return (
    <Layout>
      <Hero
        title="Getting Started"
        subtitle="Install the CLI and start managing work with Taskulus in minutes."
        eyebrow="Quick Start"
      />

      <div className="space-y-12">
        <Section
          title="Download the tskr binary"
          subtitle="Grab the prebuilt Rust CLI for your platform."
        >
          <div className="space-y-6">
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
              Download the latest release from GitHub Releases. Replace the
              version and target with the artifact that matches your platform.
            </p>
            <CodeBlock label="Example (Linux x86_64)">
              {`curl -L -o tskr.tar.gz https://github.com/AnthusAI/Taskulus/releases/download/v0.1.0/taskulus-x86_64-unknown-linux-gnu.tar.gz
tar -xzf tskr.tar.gz
chmod +x taskulus
./taskulus --help`}
            </CodeBlock>
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
              The binary name is currently <code>taskulus</code>. We are planning
              to rename the Rust CLI to <code>tskr</code>.
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
              Install Taskulus from PyPI and use the <code>tsk</code> command.
            </p>
            <CodeBlock label="Python">
              {`python -m pip install taskulus
tsk --help`}
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
              We will publish <code>tskr</code> to crates.io once the registry
              listing is ready.
            </p>
            <CodeBlock label="Cargo (coming soon)">
              {`cargo install tskr`}
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
              {`git clone https://github.com/AnthusAI/Taskulus.git
cd Taskulus`}
            </CodeBlock>
            <CodeBlock label="Rust CLI">
              {`cd rust
cargo build --release
./target/release/taskulus --help`}
            </CodeBlock>
            <CodeBlock label="Python CLI">
              {`cd python
python -m pip install -e .
tsk --help`}
            </CodeBlock>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default GettingStartedPage;
