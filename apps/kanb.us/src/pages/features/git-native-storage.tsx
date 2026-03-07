import * as React from "react";
import { Layout, Section, Hero, FullVideoPlayer, FeaturePictogram, CodeBlock } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { getVideoById } from "../../content/videos";
import { getVideoSrc } from "../../lib/getVideoSrc";

const GitNativeStoragePage = () => {
  const featureVideo = getVideoById("git-native-storage");
  const videoPoster = featureVideo?.poster ? getVideoSrc(featureVideo.poster) : undefined;
  const videoSrc = featureVideo ? getVideoSrc(featureVideo.filename) : "";

  return (
    <Layout>
      <Hero
        eyebrow="New Feature"
        title="Git-Native Storage"
        subtitle="Your project data is plain JSON in your repository. No database to manage, no proprietary index to rebuild--just files you can read, diff, and version like any other code."
        rightPane={<FeaturePictogram type="git-native-storage" />}
        bottomPane={
          <div className="w-full flex flex-col items-center justify-center mt-12 mb-8 gap-12">
            {videoSrc ? (
              <FullVideoPlayer src={videoSrc} poster={videoPoster} videoId="git-native-storage" />
            ) : null}
          </div>
        }
      />

      <div className="space-y-12">
        <Section title="Just Files" subtitle="Every issue is a JSON file in your working tree.">
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                When you create an issue, Kanbus writes a JSON file into your repository's project directory. When you
                update an issue, it updates that file. When you delete one, the file goes away. There is no background
                daemon, no index to corrupt, and no migration to run. Your project data is always right there in the
                working tree, readable by any tool that can open a file.
              </p>
              <CodeBlock label="Terminal">
{`ls project/issues/
tsk-1.json  tsk-2.json  tsk-3.json

cat project/issues/tsk-1.json
{
  "id": "tsk-1",
  "title": "Update docs",
  "status": "open",
  "type": "task"
}`}
              </CodeBlock>
            </CardContent>
          </Card>
        </Section>

        <Section title="Version Control Built In" subtitle="Every change is a diff. Every diff is reviewable." variant="alt">
          <div className="grid gap-6 md:grid-cols-2">
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Full history for free</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Because issues live in Git, you get complete change history automatically. Who changed the status?
                  When was the description updated? Just check the log. No audit trail feature needed--Git already
                  provides one.
                </p>
              </CardContent>
            </Card>
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Branch and merge your backlog</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Create issues on a feature branch and they stay on that branch until you merge. Your project
                  management data follows the same workflow as your code--branches, pull requests, reviews, and all.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section title="Transparent Caching" subtitle="Fast reads without hidden state.">
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Kanbus maintains an optional overlay cache for performance--so listing hundreds of issues stays fast. But
                the cache is entirely disposable. Delete it any time and Kanbus rebuilds it from the files that are
                already there. There is no hidden database that silently drifts out of sync. The files in your repository
                are always the truth.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section title="Works Everywhere Git Works" subtitle="No server required. No account needed." variant="alt">
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Clone a repository and you have the full project board. Push to a remote and your teammates have it too.
                Kanbus works on any machine with Git installed--no SaaS subscription, no hosted service, no network
                dependency. Your data stays where your code lives.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section title="Learn More" subtitle="Get started with Git-native project management.">
          <Card className="p-8">
            <CardContent className="p-0 text-center">
              <p className="text-muted leading-relaxed mb-6">
                Git-native storage means your project data is as portable, reviewable, and trustworthy as your source
                code. No vendor lock-in, no proprietary formats--just files.
              </p>
              <a
                href="/docs/features/git-native-storage"
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

export default GitNativeStoragePage;
