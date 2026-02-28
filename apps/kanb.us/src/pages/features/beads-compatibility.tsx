import * as React from "react";
import { Layout, Section, Hero, FullVideoPlayer, FeaturePictogram } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { VIDEOS, getVideoById } from "../../content/videos";
import { getVideoSrc } from "../../lib/getVideoSrc";

const BeadsCompatibilityPage = () => {
  const featureVideo = getVideoById("beads-compatibility");
  const videoPoster = featureVideo?.poster ? getVideoSrc(featureVideo.poster) : undefined;
  const videoSrc = featureVideo ? getVideoSrc(featureVideo.filename) : "";

  return (
    <Layout>
      <Hero
        title="Beads Compatibility"
        subtitle="Instant Kanban board for your existing Beads projects. No migration required."
        rightPane={<FeaturePictogram type="beads-compatibility" />}
        bottomPane={
          <div className="w-full flex flex-col items-center justify-center mt-12 mb-8 gap-12">
            {videoSrc ? (
              <FullVideoPlayer src={videoSrc} poster={videoPoster} videoId="beads-compatibility" />
            ) : null}
          </div>
        }
      />

      <div className="space-y-12">
        <Section
          title="Instant Kanban Board"
          subtitle="Visualize your Beads issues immediately."
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Zero Conversion Required</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                You don't need to convert your data to get a modern project board. Kanbus reads 
                your existing Beads issue files directly, giving you an interactive Kanban board instantly.
              </p>
              <p>
                Just launch the console or install the VS Code extension. You'll get a fully interactive Kanban board
                without changing a single file format. Your existing workflow stays intact while you gain powerful
                new visualization and management capabilities.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="High Performance CLI"
          subtitle="Faster operations, zero overhead."
          variant="alt"
        >
          <div className="space-y-6">
            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Bypass the Bottlenecks</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Avoid the hassles of SQLite server syncing and performance overhead. The Kanbus CLI is written in Rust 
                  and operates directly on your data files with blazing speed. Filter, list, and update issues instantly,
                  even in large projects.
                </p>
                <p>
                  Use the CLI with your agents for rapid context gathering and updates, all while maintaining full compatibility 
                  with your existing Beads tooling. Get the performance you need without sacrificing compatibility.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Risk-Free Migration"
          subtitle="A smooth path forward."
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Stay Flexible</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                There's no "big bang" migration. You can stay with the Beads format as long as you want 
                while enjoying the benefits of the Kanbus board and CLI. Start using Kanbus features today,
                migrate your data format when it makes sense for your team.
              </p>
              <p>
                When you're ready to switch formats entirely, it's a simple operation—but you don't have to do it 
                to get value today. Your timeline, your choice.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Learn More"
          subtitle="Get started with Beads compatibility."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0 text-center">
              <p className="text-muted leading-relaxed mb-6">
                Learn how to use Kanbus with your existing Beads projects and explore migration options when you're ready.
              </p>
              <a 
                href="/docs/features/beads-compatibility" 
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

export default BeadsCompatibilityPage;
