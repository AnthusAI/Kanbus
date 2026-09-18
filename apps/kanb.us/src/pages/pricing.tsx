import * as React from "react";
import { Layout, Hero } from "../components";
import { Pricing } from "../components/Pricing";

const PricingPage = () => (
  <Layout>
    <Hero
      eyebrow="PRICING"
      title="Kanbus stays yours."
      subtitle="Run the open-source project yourself, or choose the level of help you want from Anthus."
      actions={
        <a href="/#pricing" className="cta-button px-6 py-3 text-sm transition-all hover:brightness-95">
          See the options
        </a>
      }
    />
    <Pricing />
  </Layout>
);

export default PricingPage;

export const Head = () => (
  <>
    <title>Pricing — Kanbus</title>
    <meta name="description" content="Kanbus is MIT licensed and free to run yourself. Choose managed operation, assisted setup, or professional services when you want help." />
  </>
);
