import * as React from "react";
import { Layout, Section, Hero, FullVideoPlayer } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { VIDEOS, getVideoById } from "../../content/videos";
import { getVideoSrc } from "../../lib/getVideoSrc";

const JiraSyncPage = () => {
  const featureVideo = getVideoById("jira-sync");
  const videoPoster = featureVideo?.poster ? getVideoSrc(featureVideo.poster) : undefined;
  const videoSrc = featureVideo ? getVideoSrc(featureVideo.filename) : "";

  return (
    <Layout>
      <Hero
        title="Jira Sync"
        subtitle="Pull Jira issues into your repository so coding agents always have full context—no API calls, no MCP tools, just files."
        eyebrow="Integrations"
        bottomPane={
          videoSrc ? (
            <div className="w-full flex justify-center mt-12 mb-8">
              <FullVideoPlayer src={videoSrc} poster={videoPoster} videoId="jira-sync" />
            </div>
          ) : undefined
        }
      />

      <div className="space-y-12">
        <Section
          title="Context Where Agents Can See It"
          subtitle="Coding agents work best when project context lives alongside code."
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">From Jira to Files in One Command</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Kanbus bridges Jira and your local repository by pulling issues down as plain JSON files.
                Once synced, your coding agents can read every issue, comment, assignee, and priority
                directly from the filesystem—the same way they read your source code.
              </p>
              <p>
                No MCP server. No API credentials wired into the agent. No round-trip calls during a
                session. The context is simply there, in the repository, versioned alongside your work.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="One Command to Sync"
          subtitle="Pull your entire Jira project with a single command."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Run the pull command from any directory inside your repository. Kanbus reads your
                configuration for the Jira connection details and fetches every issue in the configured project.
                Use a preview flag to see what would be written without touching any files.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Configuration"
          subtitle="Add a jira block to your config—secrets stay in environment variables."
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Non-secret configuration lives in the committed configuration file. The type mappings field lets you translate Jira's issue type names to Kanbus types, so Stories become stories, Bugs become bugs, and Workstreams become epics.
              </p>
              <p>
                Your API token and email are read from environment variables and never written to disk. Add them to a local environment file or export them from your shell.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Idempotent Updates"
          subtitle="Run the sync as often as you like—existing issues are updated, not duplicated."
          variant="alt"
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Safe to Re-run Anytime</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Each synced issue stores the originating Jira key internally. On subsequent pulls, Kanbus matches by that key and updates the existing file in place—title, description, status, comments, and priority all stay current.
              </p>
              <p>
                Kanbus IDs assigned to pulled issues are stable across runs. Parent links are resolved to local Kanbus identifiers, so your agents see the full hierarchy without knowing anything about Jira's internal structure.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="What Your Agents See"
          subtitle="Plain JSON files that any tool can read."
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">No Special Tooling Required</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Synced issues land in the project directory as standard Kanbus JSON files. Any agent that can read your source files can read your issues. Use standard Kanbus commands to list or show issues, or just point an agent at the directory and tell it to read the files.
              </p>
              <p>
                Because the issues are files in the repository, they travel with the branch, survive offline work, and never require a network call during an agent session. The sync step happens once; the context is available forever after.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Learn More"
          subtitle="Ready to set up Jira sync in your repository?"
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0 text-center">
              <p className="text-muted leading-relaxed mb-6">
                See the complete documentation for step-by-step configuration, command reference, and advanced usage patterns.
              </p>
              <a 
                href="/docs/features/jira-sync" 
                className="cta-button px-6 py-3 text-sm transition-all hover:brightness-95"
              >
                Read the Documentation →
              </a>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default JiraSyncPage;
