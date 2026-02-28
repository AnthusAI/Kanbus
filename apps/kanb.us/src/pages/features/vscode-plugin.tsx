import * as React from "react";
import { Layout, Section, Hero, FullVideoPlayer, FeaturePictogram } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { VIDEOS, getVideoById } from "../../content/videos";
import { getVideoSrc } from "../../lib/getVideoSrc";

const VSCodePluginPage = () => {
  const featureVideo = getVideoById("vscode-plugin");
  const videoPoster = featureVideo?.poster ? getVideoSrc(featureVideo.poster) : undefined;
  const videoSrc = featureVideo ? getVideoSrc(featureVideo.filename) : "";

  return (
    <Layout>
      <Hero
        title="VS Code Integration"
        subtitle="Manage your project without leaving your code. The full Kanbus experience, embedded in your editor."
        rightPane={<FeaturePictogram type="vscode-plugin" />}
        bottomPane={
          <div className="w-full flex flex-col items-center justify-center mt-12 mb-8 gap-12">
            {videoSrc ? (
              <FullVideoPlayer src={videoSrc} poster={videoPoster} videoId="vscode-plugin" />
            ) : null}
          </div>
        }
      />

      <div className="space-y-12">
        <Section
          title="Seamless Workflow"
          subtitle="A dedicated Kanban board inside VS Code."
        >
          <div className="space-y-8">
            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Zero Context Switching</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-6 text-muted leading-relaxed">
                <p>
                  Open your project board in a VS Code tab. Drag issues, edit details, and filter tasks 
                  while your code remains visible in the next pane. No more alt-tabbing to the browser,
                  no more losing your place in the code. Everything you need, right where you work.
                </p>
                <div className="rounded-xl overflow-hidden shadow-lg/50 aspect-video bg-card/50 flex items-center justify-center">
                  <span className="text-muted font-medium">Screenshot: Board in VS Code Tab</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Code & Context"
          subtitle="Link your work directly to your files."
          variant="alt"
        >
          <div className="grid gap-6 md:grid-cols-2">
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Quick Access</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Access the board from the Activity Bar or Command Palette. One command, instant access
                  to your entire project workflow without leaving your editor.
                </p>
              </CardContent>
            </Card>
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">File Navigation</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Click an issue ID in a comment or commit message to jump straight to the details.
                  Your code and your tasks stay connected, making it easy to track what you're working on
                  and where you're working on it.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Get Started"
          subtitle="Install from the Marketplace."
        >
          <Card className="p-8">
            <div className="flex flex-col items-center text-center space-y-6">
              <div className="rounded-xl overflow-hidden shadow-lg/50 aspect-[2/1] w-full max-w-lg bg-card/50 flex items-center justify-center">
                <span className="text-muted font-medium">Screenshot: Extension Marketplace Page</span>
              </div>
              <p className="text-muted max-w-lg">
                The Kanbus extension is open source and available for free.
              </p>
              <a 
                href="#" 
                className="cta-button px-6 py-3 text-sm transition-all hover:brightness-95"
              >
                Install for VS Code
              </a>
            </div>
          </Card>
        </Section>

        <Section
          title="Learn More"
          subtitle="Master the VS Code integration."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0 text-center">
              <p className="text-muted leading-relaxed mb-6">
                Explore installation guides, keyboard shortcuts, and advanced features for the VS Code extension.
              </p>
              <a 
                href="/docs/features/vscode-plugin" 
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

export default VSCodePluginPage;
