import * as React from "react";
import { Layout, Section, Hero, FullVideoPlayer, FeaturePictogram } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { VIDEOS, getVideoById } from "../../content/videos";
import { getVideoSrc } from "../../lib/getVideoSrc";

const LocalTasksPage = () => {
  const featureVideo = getVideoById("local-tasks");
  const videoPoster = featureVideo?.poster ? getVideoSrc(featureVideo.poster) : undefined;
  const videoSrc = featureVideo ? getVideoSrc(featureVideo.filename) : "";

  return (
    <Layout>
      <Hero
        title="Local Tasks"
        subtitle="Keep personal or exploratory issues on your machine without committing them—then promote them to the shared project when they're ready."
        rightPane={<FeaturePictogram type="local-tasks" />}
        bottomPane={
          <div className="w-full flex flex-col items-center justify-center mt-12 mb-8 gap-12">
            {videoSrc ? (
              <FullVideoPlayer src={videoSrc} poster={videoPoster} videoId="local-tasks" />
            ) : null}
          </div>
        }
      />

      <div className="space-y-12">
        <Section
          title="Your Private Scratchpad"
          subtitle="Keep exploratory work separate until it's ready to share."
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Sometimes you need to jot down ideas, explore a wild hypothesis, or track personal reminders without cluttering the team's shared board. Local tasks give you a private workspace that lives right alongside your shared project—visible to you, invisible to version control.
              </p>
              <p>
                When you create a local task, Kanbus stores it in a special directory that never gets committed. Your teammates won't see your half-baked experiments or personal notes, but you'll still see everything together in your own view. It's like having a private notebook that sits next to the team's whiteboard.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Seamless Promotion"
          subtitle="Move from private to shared with a single command."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                The magic happens when your experiment turns into something real. With one command, you can promote a local task to the shared project. All your notes, history, and context move with it—no copying, no manual file moves, no risk of losing anything. What was private becomes public instantly, ready for your team to see and collaborate on.
              </p>
              <p>
                You can also go the other way. If a shared task needs to become a private exploration—maybe you're taking it off the public board temporarily or doing a speculative rewrite—you can localize it just as easily. The task disappears from version control but stays in your workspace.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Clean Team Views"
          subtitle="See everything together, or filter to what matters."
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                By default, Kanbus shows you both shared and local tasks together. You get the full picture of everything you're working on, whether it's committed to the repo or just living on your machine. But when you need to focus—or when you're sharing a task list with a teammate—you can filter to show only shared work, hiding your private scratchpad entirely.
              </p>
              <p>
                Or flip it around: view only your local tasks to see your personal backlog at a glance. It's your workspace, and you control what you see.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Automatic Privacy"
          subtitle="Kanbus handles the details so you don't have to."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                The first time you create a local task, Kanbus sets everything up automatically. It creates the right directory structure and updates your gitignore file to ensure your private work stays private. You don't need to remember any special configuration or worry about accidentally committing personal notes—Kanbus takes care of it.
              </p>
              <p>
                This works whether you're using Kanbus's native storage or working with Beads-backed projects. The same simple workflow applies everywhere, so you can focus on your work instead of managing file locations.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Learn More"
          subtitle="Ready to start using local tasks?"
        >
          <Card className="p-8">
            <CardContent className="p-0 text-center">
              <p className="text-muted leading-relaxed mb-6">
                Local tasks help you keep your workspace organized while maintaining a clean, focused view for your team. Whether you're exploring new ideas, tracking personal reminders, or temporarily pulling work off the shared board, local tasks give you the flexibility to work the way you want.
              </p>
              <a 
                href="/docs/features/local-tasks" 
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

export default LocalTasksPage;
