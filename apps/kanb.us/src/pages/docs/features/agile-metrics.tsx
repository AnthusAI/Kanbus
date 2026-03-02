import * as React from "react";
import { DocsLayout } from "../../../components";
import { PageProps } from "gatsby";

const DocsAgileMetricsPage = ({ location }: PageProps) => {
  return (
    <DocsLayout currentPath={location.pathname}>
      <div className="space-y-8">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground tracking-tight">Agile Metrics</h1>
          <p className="mt-4 text-xl text-muted leading-relaxed">
            A filter-aware metrics view for quick issue health checks in the console.
          </p>
        </div>

        <div className="mt-6">
          <a
            href="/features/agile-metrics"
            className="inline-flex items-center gap-2 text-sm text-muted hover:text-foreground transition-colors"
          >
            <span>←</span>
            <span>Back to Agile Metrics feature page</span>
          </a>
        </div>

        <div className="prose prose-slate max-w-none text-muted leading-relaxed space-y-6">
          <p>
            Agile Metrics provides a compact analytics panel inside the Kanbus console. It uses the same
            live snapshot as the board and recalculates from your active filters, so totals and charts
            stay consistent with what you are currently viewing.
          </p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            What Is Included
          </h2>
          <ul className="list-disc pl-5 space-y-2 mt-4">
            <li><strong>Total Issues:</strong> Count of all issues in the current filtered context.</li>
            <li><strong>Status Breakdown:</strong> Open, in progress, blocked, done, and closed tallies.</li>
            <li><strong>Project Breakdown:</strong> Per-project counts when multiple projects are present.</li>
            <li><strong>Scope Breakdown:</strong> Shared versus local issue counts.</li>
            <li><strong>Type Chart:</strong> Stacked bars for each issue type segmented by status.</li>
          </ul>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            How To Use It
          </h2>
          <p>
            Use the Board/Metrics toggle in the console header to switch views. Any project filters,
            scope toggles, or other visibility controls remain active, and the metrics panel updates
            immediately to reflect those constraints.
          </p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Interpretation Tips
          </h2>
          <ul className="list-disc pl-5 space-y-2 mt-4">
            <li>Large open counts with low in-progress counts often indicate queue buildup.</li>
            <li>A high blocked segment in one type can highlight dependency bottlenecks.</li>
            <li>Project imbalance can show where most delivery risk is concentrated.</li>
            <li>Scope distribution helps ensure local work is promoted when ready.</li>
          </ul>
        </div>
      </div>
    </DocsLayout>
  );
};

export default DocsAgileMetricsPage;
