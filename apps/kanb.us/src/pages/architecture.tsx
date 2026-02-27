import * as React from "react";
import { Layout, Section, Hero } from "../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const ArchitecturePage = () => {
  return (
    <Layout>
      <Hero
        title="Architecture"
        subtitle="Kanbus treats Gherkin as high-level source code and treats implementation code as generated artifacts."
        eyebrow="System Design"
      />

      <div className="space-y-12">
        <Section
          title="Spec-Driven Design"
          subtitle="Gherkin features are treated as high-level source code."
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">Gherkin as Source Code</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Kanbus treats its Gherkin features as high-level source code. The specifications are
                authoritative, and implementations are generated artifacts that must conform to them.
              </p>
              <p>
                This is an extreme form of behavior-driven design: the Gherkin code is not derived from
                the implementation, it defines it.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Single Source of Truth"
          subtitle="A shared features directory keeps behavior in lockstep."
          variant="alt"
        >
          <Card className="p-8">
            <CardHeader className="p-0 mb-4">
              <h3 className="text-xl font-bold text-foreground">One Shared Features Folder</h3>
            </CardHeader>
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                Kanbus maintains a single <code>features/</code> directory for behavior specifications.
                Both the Python and Rust implementations consume the exact same feature files.
              </p>
              <p>
                This keeps parity at the specification level and prevents behavior drift between languages.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Multi-Target Implementations"
          subtitle="Multiple languages, identical behavior."
        >
          <div className="grid gap-8 md:grid-cols-2">
            <Card className="p-8">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Python</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                The Python implementation is designed for fast iteration and agent integration while remaining
                fully constrained by the shared behavior specifications.
              </CardContent>
            </Card>
            <Card className="p-8">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Rust</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                The Rust implementation targets performance and reliability while staying behaviorally identical
                to the Python build through the same Gherkin specs.
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Operational Implications"
          subtitle="How spec-driven design shapes development."
          variant="alt"
        >
          <div className="grid gap-8 md:grid-cols-2">
            <Card className="p-8">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Feature Work Starts With Gherkin</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Every behavior change begins with a specification update. Code exists to satisfy specs, not the other way around.
              </CardContent>
            </Card>
            <Card className="p-8">
              <CardHeader className="p-0 mb-3">
                <h3 className="text-xl font-bold text-foreground">Parity Is Non-Negotiable</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Shared specifications plus parity checks ensure behavior remains identical across implementations.
              </CardContent>
            </Card>
          </div>
        </Section>
      </div>
    </Layout>
  );
};

export default ArchitecturePage;
