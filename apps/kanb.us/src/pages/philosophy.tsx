import * as React from "react";
import { Layout, Section, Hero } from "../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const PhilosophyPage = () => {
  return (
    <Layout>
      <Hero
        title="Design Philosophy"
        subtitle="Kanbus is built on a set of core principles that prioritize developer experience, transparency, and longevity."
      />

      <div className="space-y-12">
        <Section
          title="Why Kanbus Exists"
          subtitle="Game-changing technology for the age of AI agents."
        >
          <Card className="p-8 bg-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">The Sleep Factor</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                The motivation for Kanbus came from a simple need: to offload mental context. When you are juggling
                dozens of open loops—chat sessions, pending tasks, architectural decisions—you need a place to put
                them that doesn't require logging in or managing infrastructure.
              </p>
              <p>
                Kanbus allows you (and your AI agents) to dump context immediately into the repository. It's the
                difference between keeping 15 plates spinning in your head and putting them on a shelf.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Inspiration & Lineage"
          subtitle="Standing on the shoulders of giants."
          variant="alt"
        >
          <Card className="p-8 bg-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">A Spiritual Successor to Beads</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                This project was inspired by{" "}
                <a href="https://github.com/steveyegge/beads" className="text-selected hover:underline">
                  Beads
                </a>{" "}
                and is intended as a spiritual successor that embraces the elegant domain-specific cognitive framework it
                pioneered. We are deeply grateful to the Beads author and community for proving the concept so well.
              </p>
              <p>Kanbus represents the next generation of this idea, improved for the era of AI agents:</p>
              <ul className="list-disc list-inside space-y-2 ml-4">
                <li>
                  <strong>Thinner layer over Git:</strong> We removed the secondary SQLite database to eliminate
                  synchronization complexity.
                </li>
                <li>
                  <strong>Git-aligned storage:</strong> Separate files for separate tasks mean no merge conflicts when
                  agents work in parallel.
                </li>
                <li>
                  <strong>Focused Cognitive Model:</strong> We stripped away 100+ unused attributes to focus on the core
                  cognitive framework, reducing context pollution for AI models.
                </li>
                <li>
                  <strong>Standard Nomenclature:</strong> We use standard terms (Epics, Tasks) to leverage the massive
                  pre-training AI models already have on these concepts.
                </li>
              </ul>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Core Principles"
          subtitle="The fundamental rules that guide the development of the Kanbus system."
        >
          <div className="grid gap-8 md:grid-cols-2">
            {[
              {
                title: "1. Files are the database",
                body:
                  "There is no hidden SQLite file, no background daemon, and no remote API. The state of your project is strictly defined by the JSON files in your repository. Each command scans those files directly—the files are the truth."
              },
              {
                title: "2. One File Per Issue",
                body:
                  "Other systems store everything in a single JSONL file. This guarantees merge conflicts when two people (or agents) work on different tasks simultaneously. Kanbus splits every issue into its own file, letting Git handle the merging naturally."
              },
              {
                title: "3. Helpful Cognitive Model",
                body:
                  "The task model should unburden your mind, not add to it. We stripped away 100+ unused attributes to focus on a core, elegant framework (Status, Priority, Dependencies). This helps AI agents focus on solving problems, not navigating the tool."
              },
              {
                title: "4. Agent-Native",
                body:
                  "Kanbus is basically Jira + Confluence for agents. The CLI allows agents to read the current state of the world, and the Wiki engine allows them to read dynamic summaries of initiatives. It is designed to be the memory bank for your AI workforce."
              },
              {
                title: "5. Git-Native Scoping",
                body:
                  "We don't need complex roles to handle private tasks. Just use .gitignore. Kanbus respects your directory structure: run it at the root to see everything, or in a subfolder to focus on that module. It leverages the tools you already use."
              }
            ].map((card) => (
              <Card key={card.title} className="p-8 bg-card">
                <CardHeader className="p-0 mb-3">
                  <h3 className="text-xl font-bold text-foreground">{card.title}</h3>
                </CardHeader>
                <CardContent className="p-0 text-muted leading-relaxed">{card.body}</CardContent>
              </Card>
            ))}
          </div>
        </Section>

        <Section
          title="Architecture"
          subtitle="How Kanbus works under the hood."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-2">
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">No Friction</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Git hooks should help you, not block you. Kanbus removes the concept of syncing entirely. There is no
                secondary database to maintain, so you are never blocked from pushing your code.
              </CardContent>
            </Card>
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">The Wiki Engine</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                The wiki command renders Markdown templates using the Jinja2 engine. It injects a project context object
                that gives you access to the entire issue graph. This allows you to write living documents that always
                reflect the latest status.
              </CardContent>
            </Card>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default PhilosophyPage;
