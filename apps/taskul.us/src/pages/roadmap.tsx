import * as React from "react";
import { Layout, Section } from "../components";

const RoadmapPage = () => {
  return (
    <Layout>
      <div className="page">
        <div className="container grid">
          <Section
            title="Roadmap"
            subtitle="Public milestones for the Taskulus release plan."
          >
            <div className="grid two">
              <div className="card">
                <h3>M1: Minimal tracker</h3>
                <p>Create, update, close, and delete issues.</p>
              </div>
              <div className="card">
                <h3>M2: Planning ready</h3>
                <p>Query, filter, and search issues for planning.</p>
              </div>
              <div className="card">
                <h3>M3: Self-hosting</h3>
                <p>Wiki system supports Taskulus tracking itself.</p>
              </div>
              <div className="card">
                <h3>M4: Release</h3>
                <p>Migration, polish, and installation paths complete.</p>
              </div>
            </div>
          </Section>
          <Section
            title="Contribute"
            subtitle="Help validate specs and implementation parity."
            variant="alt"
          >
            <div className="card">
              <h3>Open tasks</h3>
              <p>
                The Taskulus repo is managed in Beads with a shared task board.
              </p>
            </div>
          </Section>
        </div>
      </div>
    </Layout>
  );
};

export default RoadmapPage;
