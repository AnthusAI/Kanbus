import * as React from "react";
import AnthusFooter from "anthus-footer";
import { FEATURE_ENTRIES } from "../content/features";

const SiteFooter = () => {
  const featureLinks = FEATURE_ENTRIES.slice(0, 8).map((feature) => ({
    label: feature.title,
    href: feature.href,
    external: false,
  }));

  return (
    <AnthusFooter
      siteId="kanbus"
      subtitle="Part of the Anthus Platform"
      description="Kanbus orchestrates AI agent workloads with durable boards, workflow visibility, and operational guardrails for multi-agent delivery."
      byline="Built by Anthus AI Solutions"
      additionalColumns={[
        {
          title: "Features",
          links: featureLinks,
        },
        {
          title: "Reference",
          links: [
            { label: "What Is This?", href: "/what-is-this", external: false },
            { label: "Documentation", href: "/docs", external: false },
            { label: "Philosophy", href: "/philosophy", external: false },
            { label: "GitHub", href: "https://github.com/AnthusAI/Kanbus" },
          ],
        },
      ]}
    />
  );
};

export default SiteFooter;
