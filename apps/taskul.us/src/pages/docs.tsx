import * as React from "react";
import { Layout, Section } from "../components";

const DocsPage = () => {
  return (
    <Layout>
      <div className="page">
        <div className="container grid">
          <Section
            title="Documentation"
            subtitle="Guides for installation, configuration, and daily workflows."
          >
            <div className="grid two">
              <div className="card">
                <h3>Getting Started</h3>
                <p>Install Taskulus and create your first issue.</p>
              </div>
              <div className="card">
                <h3>CLI Reference</h3>
                <p>Every command and flag in one place.</p>
              </div>
              <div className="card">
                <h3>Configuration</h3>
                <p>Define hierarchies, workflows, and defaults.</p>
              </div>
              <div className="card">
                <h3>Wiki Guide</h3>
                <p>Build planning docs with live issue data.</p>
              </div>
            </div>
          </Section>
          <Section
            title="Stay in sync"
            subtitle="Both implementations follow the same behavior specifications."
            variant="alt"
          >
            <div className="card">
              <h3>Shared specs</h3>
              <p>
                Gherkin scenarios define the product. Python and Rust stay in
                parity through the same feature suite.
              </p>
            </div>
          </Section>
        </div>
      </div>
    </Layout>
  );
};

export default DocsPage;
