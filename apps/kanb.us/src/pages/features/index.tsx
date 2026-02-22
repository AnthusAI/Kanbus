import * as React from "react";
import { Layout, Section, Hero } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { FEATURE_ENTRIES } from "../../content/features";

const FeaturesPage = () => {
  return (
    <Layout>
      <Hero
        title="Features"
        subtitle="Focused capabilities for modern development workflows."
        eyebrow="Key Capabilities"
      />

      <div className="space-y-12">
        <Section
          title="Features"
          subtitle="Explore the feature set in detail."
        >
          <div className="grid gap-6 md:grid-cols-2">
            {FEATURE_ENTRIES.map((feature) => (
              <a key={feature.href} href={feature.href} className="group">
                <Card className="p-6 shadow-card transition-transform group-hover:-translate-y-1">
                  <CardHeader className="p-0 mb-3">
                    <h3 className="text-xl font-bold text-foreground">{feature.title}</h3>
                  </CardHeader>
                  <CardContent className="p-0 text-muted leading-relaxed">
                    {feature.description}
                  </CardContent>
                </Card>
              </a>
            ))}
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default FeaturesPage;
