import * as React from "react";
import { Layout, Section, Hero, FullVideoPlayer, FeaturePictogram } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { getVideoById } from "../../content/videos";
import { getVideoSrc } from "../../lib/getVideoSrc";

const VirtualProjectsPage = () => {
  const featureVideo = getVideoById("virtual-projects");
  const videoPoster = featureVideo?.poster ? getVideoSrc(featureVideo.poster) : undefined;
  const videoSrc = featureVideo ? getVideoSrc(featureVideo.filename) : "";

  return (
    <Layout>
      <Hero
        title="Virtual Projects"
        subtitle="View and manage issues from multiple repositories in a single workspace."
        rightPane={<FeaturePictogram type="virtual-projects" />}
        bottomPane={
          <div className="w-full flex flex-col items-center justify-center mt-12 mb-8 gap-12">
            {videoSrc ? (
              <FullVideoPlayer src={videoSrc} poster={videoPoster} videoId="virtual-projects" />
            ) : null}
          </div>
        }
      />

      <div className="space-y-12">
        <Section
          title="One View, Many Projects"
          subtitle="Don't context switch between repositories."
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Unified Workflow</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Kanbus allows you to mount other Kanbus projects into your current workspace as "virtual projects".
                This aggregates issues from all configured projects into a single list, so you can query, filter,
                and track work across your entire stack without changing directories.
              </p>
              <p>
                Virtual projects are perfect for microservices architectures where work spans multiple repos,
                library authors tracking issues in both the library and consuming apps, and release managers
                overseeing multiple related projects. One command, complete visibility.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Shared Configuration"
          subtitle="Team-wide visibility via configuration files."
          variant="alt"
        >
          <div className="space-y-6">
            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">For the Whole Team</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  To make a virtual project available to everyone working on the repository, add it to your
                  configuration file. Now, when anyone runs a command, they will see issues from the main project
                  alongside issues from all virtual projects.
                </p>
                <p>
                  Everyone gets the same unified view automatically. No individual setup required, no confusion
                  about which issues belong where. The entire team stays aligned.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Local Overrides"
          subtitle="Private configurations for your personal workflow."
        >
          <div className="space-y-6">
            <Card className="p-8">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Personal Customization</h3>
              </CardHeader>
              <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
                <p>
                  Sometimes you need to see issues from a dependency that isn't part of the official project structure—for example,
                  debugging a library you're locally linking. You can add virtual projects just for yourself using a
                  personal override file.
                </p>
                <p>
                  This file is git-ignored by default, so your personal setup won't affect other team members.
                  Kanbus merges this configuration with the main project settings, giving you a super-set of all projects
                  tailored to your workflow.
                </p>
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Learn More"
          subtitle="Set up virtual projects for your workflow."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0 text-center">
              <p className="text-muted leading-relaxed mb-6">
                Get step-by-step instructions, configuration examples, and best practices for managing multi-repo workflows.
              </p>
              <a 
                href="/docs/features/virtual-projects" 
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

export default VirtualProjectsPage;
