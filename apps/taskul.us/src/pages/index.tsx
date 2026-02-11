import * as React from "react";
import { Layout, Section } from "../components";

const IndexPage = () => {
  return (
    <Layout>
      <div className="page">
        <div className="container grid">
          <Section
            title="One spec, two implementations"
            subtitle="Taskulus ships in Python and Rust, both driven by the same behavior specifications."
          >
            <div className="grid two">
              <div className="card">
                <h3>Python</h3>
                <p>Fast iteration and easy installation for teams in Python.</p>
              </div>
              <div className="card">
                <h3>Rust</h3>
                <p>High-performance builds for large repositories.</p>
              </div>
            </div>
          </Section>
          <Section
            title="Files are the database"
            subtitle="Every issue is a JSON file, visible in your repo and versioned alongside code."
            variant="alt"
          >
            <div className="grid two">
              <div className="card">
                <h3>Readable by humans</h3>
                <p>Open a file and see the full issue context without a server.</p>
              </div>
              <div className="card">
                <h3>Safe by default</h3>
                <p>Strict workflows and hierarchy validation prevent drift.</p>
              </div>
            </div>
          </Section>
          <Section
            title="Planning that stays current"
            subtitle="Jinja-driven wiki pages render live issue data into narrative docs."
          >
            <div className="grid two">
              <div className="card">
                <h3>Live status</h3>
                <p>Counts, readiness, and dependencies update automatically.</p>
              </div>
              <div className="card">
                <h3>Strategy first</h3>
                <p>Keep roadmaps and plans aligned with real work.</p>
              </div>
            </div>
          </Section>
        </div>
      </div>
    </Layout>
  );
};

export default IndexPage;
