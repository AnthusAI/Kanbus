import * as React from "react";
import { Layout, Section, Hero, FeaturePictogram } from "../../components";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const AgileMetricsPage = () => {
  return (
    <Layout>
      <Hero
        title="Agile Metrics"
        subtitle="Review issue health instantly with status, type, project, and scope metrics that respect your active filters."
        rightPane={<FeaturePictogram type="agile-metrics" />}
      />

      <div className="space-y-12">
        <Section
          title="Snapshot At A Glance"
          subtitle="See how much work exists and where it currently sits."
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                The metrics panel summarizes your current issue set with a total count and a status
                distribution. It updates from the same live snapshot pipeline as the board, so your
                numbers stay aligned with what the team is working on right now.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Breakdowns That Stay Useful"
          subtitle="Group work by type, project, and source without leaving the console."
          variant="alt"
        >
          <div className="grid gap-6 md:grid-cols-2">
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Type + Status Chart</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Stacked bars show each issue type with status segments, making imbalances obvious when
                a workflow is overloaded in open or blocked states.
              </CardContent>
            </Card>
            <Card className="p-8 bg-card">
              <CardHeader className="p-0 mb-4">
                <h3 className="text-xl font-bold text-foreground">Project + Scope Counts</h3>
              </CardHeader>
              <CardContent className="p-0 text-muted leading-relaxed">
                Separate counts by project key and source scope (shared versus local) so you can quickly
                validate whether a board view is dominated by one area of work.
              </CardContent>
            </Card>
          </div>
        </Section>

        <Section
          title="Filter-Aware By Design"
          subtitle="Metrics always reflect your active project and visibility filters."
        >
          <Card className="p-8">
            <CardContent className="p-0 space-y-4 text-muted leading-relaxed">
              <p>
                The metrics panel uses the same filtered issue set that drives the board. If you narrow
                to a specific project or hide local issues, your totals and chart values recalculate to
                match that context immediately.
              </p>
            </CardContent>
          </Card>
        </Section>

        <Section
          title="Learn More"
          subtitle="Read the complete Agile Metrics documentation."
          variant="alt"
        >
          <Card className="p-8">
            <CardContent className="p-0 text-center">
              <p className="text-muted leading-relaxed mb-6">
                Get the full reference for interpreting each section of the metrics view.
              </p>
              <a
                href="/docs/features/agile-metrics"
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

export default AgileMetricsPage;
