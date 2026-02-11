import * as React from "react";
import { Layout, Section } from "../components";

const ProductPage = () => {
  return (
    <Layout>
      <div className="page">
        <div className="container grid">
          <Section
            title="Product overview"
            subtitle="Taskulus is a git-native project management system that lives with your code."
          >
            <div className="grid two">
              <div className="card">
                <h3>Issue tracking</h3>
                <p>Hierarchies, workflows, dependencies, and comments.</p>
              </div>
              <div className="card">
                <h3>Wiki system</h3>
                <p>Markdown templates with live issue data for planning.</p>
              </div>
              <div className="card">
                <h3>Local index</h3>
                <p>Fast queries from an in-memory cache, no daemon.</p>
              </div>
              <div className="card">
                <h3>CLI first</h3>
                <p>Single command surface for init, create, update, and search.</p>
              </div>
            </div>
          </Section>
          <Section
            title="Why teams choose Taskulus"
            subtitle="Less process overhead, more clarity, no hosted dependencies."
            variant="alt"
          >
            <div className="grid two">
              <div className="card">
                <h3>Git-native</h3>
                <p>All data is versioned with your codebase.</p>
              </div>
              <div className="card">
                <h3>Transparent</h3>
                <p>Readable JSON and Markdown means no vendor lock-in.</p>
              </div>
            </div>
          </Section>
        </div>
      </div>
    </Layout>
  );
};

export default ProductPage;
