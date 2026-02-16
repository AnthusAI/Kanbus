import * as React from "react";
import { Layout, Section, Hero } from "../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const FeaturesPage = () => {
  return (
    <Layout>
      <Hero
        title="Features"
        subtitle="What makes Kanbus effective for modern development workflows."
        eyebrow="Key Capabilities"
      />

      <div className="space-y-12">
        <Section
          title="Unique ID Generation"
          subtitle="Collision-free identifiers for concurrent workflows."
        >
          <Card className="p-8 shadow-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Hash-Based IDs vs. Sequential Numbering</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Kanbus assigns hash-based unique IDs to each issue to avoid collisions during concurrent edits.
                When multiple agents or team members create issues in parallel, each ID is globally unique
                from the moment of creation.
              </p>
              <p>
                This design choice eliminates merge conflicts that can occur when two developers create
                issues at the same time in different branches. No coordination needed—just create and merge.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Shared Datastore Support"
          subtitle="Multi-project collaboration with namespace safety."
          variant="alt"
        >
          <Card className="p-8 shadow-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Per-Project Keys with Centralized Storage</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Multiple projects can point to a shared data store while keeping a configurable project_key
                per repository to prevent collisions. Track work across codebases with centralized visibility
                and per-project namespacing.
              </p>
              <p>
                This enables organizations to maintain a single source of truth for all issues while
                ensuring that project-specific concerns remain properly isolated. Each project's issues
                are namespaced by its unique key, allowing safe concurrent operations across repositories.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Colorized CLI Output"
          subtitle="Consistent, color-aware terminal interface."
        >
          <Card className="p-8 shadow-card">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Controlled Terminal Formatting</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Kanbus create and show commands produce consistent, color-aware output that respects
                your terminal capabilities. The --porcelain flag provides machine-readable output
                without color codes when you need it.
              </p>
              <p>
                The colorized output uses semantic colors for issue types, priorities, and statuses,
                making it easier to scan large lists of issues. When piping output or running in
                CI environments, porcelain mode ensures clean, parseable text.
              </p>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default FeaturesPage;
