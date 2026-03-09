import * as React from "react";
import { Layout, Section, Hero, FeaturePictogram } from "../../components";
import { Card, CardContent } from "@kanbus/ui";
import { FEATURE_ENTRIES } from "../../content/features";

const FeaturesPage = () => {
  return (
    <Layout>
      <Hero
        title="Features"
        subtitle="Focused capabilities that make Kanbus practical for daily work."
      />

      <div className="space-y-12">
        {FEATURE_ENTRIES.map((feature, i) => {
          const videoId = feature.href.split("/").pop() || "";
          return (
            <Section key={feature.href} variant={i % 2 === 1 ? "alt" : undefined}>
              <a href={feature.href} className="group block">
                <Card className="p-0 overflow-hidden transition-transform group-hover:-translate-y-1">
                  <div className="flex flex-col md:flex-row">
                    <div className="md:w-2/5 aspect-video md:aspect-auto bg-background flex items-center justify-center overflow-hidden">
                      <FeaturePictogram
                        type={videoId}
                        className="w-full h-full min-h-0"
                        style={{ minHeight: "100%", borderRadius: 0 }}
                      />
                    </div>
                    <CardContent className="md:w-3/5 p-6 md:p-8 flex flex-col justify-center">
                      <h3 className="text-2xl font-bold text-foreground mb-4 group-hover:text-selected transition-colors">
                        {feature.title}{" "}
                        <span className="inline-block transition-transform group-hover:translate-x-1">
                          →
                        </span>
                      </h3>
                      {feature.detailedDescription ? (
                        <div className="space-y-3 text-muted leading-relaxed">
                          {feature.detailedDescription.map((paragraph, j) => (
                            <p key={j}>{paragraph}</p>
                          ))}
                        </div>
                      ) : (
                        <p className="text-muted leading-relaxed">
                          {feature.description}
                        </p>
                      )}
                    </CardContent>
                  </div>
                </Card>
              </a>
            </Section>
          );
        })}

        <Section variant="alt">
          <Card className="p-8">
            <CardContent className="p-0 text-center">
              <p className="text-muted leading-relaxed mb-6">
                Ready to dive deeper? Explore the complete documentation for CLI
                commands, configuration options, and advanced workflows.
              </p>
              <a
                href="/docs"
                className="cta-button px-6 py-3 text-sm transition-all hover:brightness-95"
              >
                View Documentation →
              </a>
            </CardContent>
          </Card>
        </Section>
      </div>
    </Layout>
  );
};

export default FeaturesPage;
