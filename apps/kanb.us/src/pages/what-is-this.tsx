import * as React from "react";
import { Layout, Section, Hero, FeaturePictogram } from "../components";
import { Card, CardContent } from "@kanbus/ui";

const WhatIsThisPage = () => {
  return (
    <Layout>
      <Hero
        eyebrow="Start Here"
        title="What Is This?"
        subtitle="Kanbus is a simple way to keep project context with your code so people and AI helpers can pick up where you left off."
        actions={
          <>
            <a
              href="/getting-started"
              className="cta-button px-6 py-3 text-sm transition-all hover:brightness-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
            >
              Getting Started
            </a>
            <a
              href="/features"
              className="text-sm font-semibold leading-6 text-foreground hover:text-selected transition-all"
            >
              See Features <span aria-hidden="true">-&gt;</span>
            </a>
          </>
        }
      />

      <div className="space-y-12">
        <Section
          title="Why this exists"
          subtitle="Work context gets lost when it lives in chats, docs, or someone's head."
        >
          <Card className="p-8 bg-card">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                When you ask an AI assistant for help, you end up with instructions and decisions scattered across chat
                logs, sticky notes, and temporary files.
              </p>
              <p>
                Switch computers or tools, and that context disappears. Hand a task to a teammate, and they have to
                rebuild the story from scratch.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="In plain English"
          subtitle="A shared project notebook that lives with your code."
          variant="alt"
        >
          <Card className="p-8 bg-card">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Kanbus stores tasks as small files right next to your code. That makes your repository the source of
                truth, and Git becomes the paper trail.
              </p>
              <p>
                Any tool can read those files: a CLI, a board in your editor, or an AI helper. Everyone sees the same
                story.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Why Kanban?"
          subtitle="A simple visual flow that started on Toyota factory floors and now powers tools like Jira."
        >
          <Card className="p-8 bg-card">
            <CardContent className="p-0 grid gap-8 md:grid-cols-2 items-center text-muted leading-relaxed">
              <div className="space-y-4">
                <p>
                  Kanban means "signboard" in Japanese. Toyota used it to visualize work-in-progress on the factory
                  floor so teams could see what was blocked, what was next, and keep flow steady.
                </p>
                <p>
                  Modern tools like Jira popularized the same pattern for software: columns for <strong>To Do</strong>,
                  <strong> In Progress</strong>, and <strong>Done</strong>. Kanbus keeps that familiar board but stores the
                  cards as plain files in your repo, so developers and AI helpers see the exact same source of truth.
                </p>
              </div>
              <div className="flex justify-center">
                <div className="w-full max-w-[360px] aspect-[5/3] rounded-xl bg-card-muted border border-border/60 p-4">
                  <FeaturePictogram type="kanban-board" className="w-full h-full" />
                </div>
              </div>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="What it's good at"
          subtitle="Practical wins you feel immediately."
        >
          <Card className="p-8 bg-card">
            <CardContent className="p-0 text-muted leading-relaxed">
              <ul className="list-disc list-inside space-y-2">
                <li>Handing off work without losing context</li>
                <li>Switching computers or AI tools without re-explaining everything</li>
                <li>Keeping private scratch notes locally and sharing when ready</li>
                <li>Pulling Jira issues into your repo so agents can work on them</li>
                <li>Keeping living docs that update from real task data</li>
              </ul>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="How you use it"
          subtitle="You keep work in one place, and your tools stay in sync."
          variant="alt"
        >
          <Card className="p-8 bg-card">
            <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
              <p>
                Create a task, add notes, and update its status. Kanbus saves those changes as files, and Git keeps the
                history.
              </p>
              <p>
                When you or an AI helper open the repo, the full context is already there.
              </p>
              <div className="flex flex-wrap items-center gap-4">
                <a
                  href="/getting-started"
                  className="cta-button px-6 py-3 text-sm transition-all hover:brightness-95"
                >
                  Getting Started
                </a>
                <a
                  href="/philosophy"
                  className="text-sm font-semibold leading-6 text-foreground hover:text-selected transition-all"
                >
                  Read the Philosophy <span aria-hidden="true">-&gt;</span>
                </a>
              </div>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default WhatIsThisPage;
