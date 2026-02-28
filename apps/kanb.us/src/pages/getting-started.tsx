import * as React from "react";
import { Layout, Section, Hero, CodeBlock } from "../components";
import { Card, CardContent } from "@kanbus/ui";

const GettingStartedPage = () => {
  return (
    <Layout>
      <Hero
        title="Getting Started"
        subtitle="Install the CLI and start managing work with Kanbus in minutes."
      />

      <div className="space-y-12">
        <Section
          title="Install with cargo"
          subtitle="Cargo installs the preferred binaries, keeping the CLI and web console in sync."
        >
          <Card className="p-8 bg-card">
            <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
              <p>
                Cargo is the recommended installation path. It publishes two crates, <code>kbs</code> (CLI)
                and <code>kbsc</code> (web console), so you can update them quickly across any Rust toolchain.
              </p>
              <CodeBlock label="Cargo (CLI)">
{`cargo install kbs
kbs --help`}
              </CodeBlock>
              <CodeBlock label="Cargo (web console)">
{`cargo install kbsc
kbsc --help`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Install with pip"
          subtitle="Use the Python CLI for rapid scripting or embedding Kanbus into Python workflows."
          variant="alt"
        >
          <Card className="p-8 bg-card">
            <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
              <p>
                Install Kanbus from PyPI and run <code>kbs</code> (a <code>kanbus</code> alias is also available).
              </p>
              <CodeBlock label="Python">
{`python -m pip install kbs
kbs --help`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Build from source"
          subtitle="Clone the repo and build the Rust and Python binaries yourself."
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
./target/release/kbs --help`}
              </CodeBlock>
              <CodeBlock label="Rust Console">
{`./target/release/kbsc --help`}
              </CodeBlock>
              <CodeBlock label="Python CLI">
{`cd python
python -m pip install -e .
kbs --help`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Download prebuilt binaries"
          subtitle="Grab the kbs and kbsc releases from GitHub if you prefer standalone archives."
          variant="alt"
        >
          <Card className="p-8 bg-card">
            <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
              <p>
                Each release archive contains a single binary. Extract, mark executable, and run <code>kbs</code> or <code>kbsc</code>.
              </p>
              <CodeBlock label="Download CLI (Linux x86_64)">
{`curl -L -o kbs.tar.gz https://github.com/AnthusAI/Kanbus/releases/latest/download/kbs-x86_64-unknown-linux-gnu.tar.gz
tar -xzf kbs.tar.gz
chmod +x kbs
./kbs --help`}
              </CodeBlock>
              <CodeBlock label="Download Console Server (Linux x86_64)">
{`curl -L -o kbsc.tar.gz https://github.com/AnthusAI/Kanbus/releases/latest/download/kbsc-x86_64-unknown-linux-gnu.tar.gz
tar -xzf kbsc.tar.gz
chmod +x kbsc
./kbsc
# Opens web UI at http://127.0.0.1:5174/`}
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
                Run <code>kbs init</code> once in the repository root. It creates
                the <code>project/</code> directory and the repo-level
                <code>.kanbus.yml</code> file.
              </p>
              <CodeBlock label="Initialize">
{`cd your-repo
git init
kbs init`}
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
{`kbs list
kbs ready`}
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
