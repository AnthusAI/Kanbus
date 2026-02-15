import * as React from "react";
import { Layout, Section, Hero, CodeBlock } from "../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

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
          <Card className="p-8 bg-card">
            <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
              <p>
                Download the latest release from GitHub Releases. Replace the
                version and target with the artifact that matches your platform.
              </p>
              <CodeBlock label="Example (Linux x86_64)">
{`curl -L -o kanbusr.tar.gz https://github.com/AnthusAI/Kanbus/releases/download/v0.1.0/kanbusr-x86_64-unknown-linux-gnu.tar.gz
tar -xzf kanbusr.tar.gz
chmod +x kanbusr
./kanbusr --help`}
              </CodeBlock>
              <p>
                The binary name is <code>kanbusr</code>.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Install with pip"
          subtitle="Use the Python CLI for fast iteration and scripting."
          variant="alt"
        >
          <Card className="p-8 bg-card">
            <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
              <p>
                Install Kanbus from PyPI and use the <code>kanbus</code> command.
              </p>
              <CodeBlock label="Python">
{`python -m pip install kanbus
kanbus --help`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Install with cargo"
          subtitle="Rust installation is coming soon."
        >
          <Card className="p-8 bg-card">
            <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
              <div className="inline-flex items-center rounded-full bg-card-muted px-3 py-1 text-xs font-semibold text-muted">
                Coming soon
              </div>
              <p>
                We will publish <code>kanbusr</code> to crates.io once the registry
                listing is ready.
              </p>
              <CodeBlock label="Cargo (coming soon)">
{`cargo install kanbusr`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Build from source"
          subtitle="Clone the repo and run directly."
          variant="alt"
        >
          <Card className="p-8 bg-card">
            <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
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
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Initialize Your Repository"
          subtitle="Create the Kanbus structure in an existing git repo."
        >
          <Card className="p-8 bg-card">
            <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
              <p>
                Run <code>kanbus init</code> once in the repository root. It creates
                the <code>project/</code> directory and the repo-level
                <code>.kanbus.yml</code> file.
              </p>
              <CodeBlock label="Initialize">
{`cd your-repo
git init
kanbus init`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Keep Configuration Updated"
          subtitle="Evolve workflows and defaults without re-running init."
          variant="alt"
        >
          <Card className="p-8 bg-card">
            <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
              <p>
                Edit <code>project/config.yaml</code> to change hierarchy,
                workflows, priorities, and defaults. Use
                <code>.kanbus.override.yml</code> for local-only settings like
                assignee or time zone.
              </p>
              <CodeBlock label="Validate">
{`kanbus list
kanbus ready`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Beads Compatibility During Transition"
          subtitle="Keep JSONL data while moving to Kanbus."
        >
          <Card className="p-8 bg-card">
            <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
              <p>
                If your repo still stores issues in <code>.beads/issues.jsonl</code>,
                enable compatibility in both config files.
              </p>
              <CodeBlock label="Compatibility">
{`.kanbus.yml
beads_compatibility: true

project/config.yaml
beads_compatibility: true`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default GettingStartedPage;
