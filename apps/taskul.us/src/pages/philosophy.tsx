import * as React from "react";
import { Layout, Section, Hero } from "../components";

const PhilosophyPage = () => {
  return (
    <Layout>
      <div className="page">
        <div className="container">
          <Hero
            title="Design Philosophy"
            subtitle="Taskulus is built on a set of core principles that prioritize developer experience, transparency, and longevity."
            eyebrow="System Design"
          />
        </div>

        <div className="container grid">
          <Section
            title="Core Principles"
            subtitle="The fundamental rules that guide the development of the Taskulus system."
          >
            <div className="grid two">
              <div className="card">
                <h3>1. Files are the database</h3>
                <p>
                  There is no hidden SQLite file or remote API. The state of your
                  project is strictly defined by the JSON files in your repository.
                  If you delete a file, the issue is gone.
                </p>
              </div>
              <div className="card">
                <h3>2. Human-readable by default</h3>
                <p>
                  You should be able to read and understand your project data
                  without the Taskulus CLI. JSON is used for data, Markdown for
                  content. IDs are short and memorable.
                </p>
              </div>
              <div className="card">
                <h3>3. Minimal schema</h3>
                <p>
                  We enforce only what is necessary for the graph to work. Everything
                  else is extensible. We don't presume to know your workflow.
                </p>
              </div>
              <div className="card">
                <h3>4. Two implementations, one spec</h3>
                <p>
                  We build in Python for scripting and Rust for performance. Both
                  are driven by a single, shared Gherkin behavior specification.
                </p>
              </div>
              <div className="card">
                <h3>5. The spec is the artifact</h3>
                <p>
                  The behavior specification IS the product definition. Code exists
                  only to satisfy the spec.
                </p>
              </div>
            </div>
          </Section>

          <Section
            title="Architecture"
            subtitle="How Taskulus works under the hood."
            variant="alt"
          >
            <div className="grid two">
              <div className="card">
                <h3>In-Memory Index</h3>
                <p>
                  Taskulus does not run a background daemon. When you run a command,
                  it scans your project files, builds an in-memory graph, performs
                  the operation, and exits.
                </p>
              </div>
              <div className="card">
                <h3>The Wiki Engine</h3>
                <p>
                  The `wiki` command renders Markdown templates using the Jinja2
                  engine. It injects a `project` context object that gives you
                  access to the entire issue graph.
                </p>
              </div>
            </div>
          </Section>
        </div>
      </div>
    </Layout>
  );
};

export default PhilosophyPage;
