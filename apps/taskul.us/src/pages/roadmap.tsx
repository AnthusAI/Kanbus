import * as React from "react";
import { Layout, Section, Hero } from "../components";

const RoadmapPage = () => {
  return (
    <Layout>
      <div className="page">
        <div className="container">
          <Hero
            title="Roadmap"
            subtitle="The path to version 1.0. We are building Taskulus in public, phase by phase."
            eyebrow="Development Plan"
          />
        </div>

        <div className="container grid">
          <Section
            title="Phase 1: Foundation"
            subtitle="Establishing the core data model and CLI interactions."
          >
            <div className="grid two">
              <div className="card">
                <h3>Repository Setup</h3>
                <p>Monorepo structure with Python and Rust workspaces sharing Gherkin specifications.</p>
              </div>
              <div className="card">
                <h3>Data Model</h3>
                <p>JSON schema for Issues, Tasks, and Comments. File I/O operations.</p>
              </div>
              <div className="card">
                <h3>In-Memory Index</h3>
                <p>Graph construction from file scan. ID generation and validation.</p>
              </div>
              <div className="card">
                <h3>CLI Workflow</h3>
                <p>Basic commands: `init`, `create`, `list`, `show`, `update`, `delete`.</p>
              </div>
            </div>
          </Section>

          <Section
            title="Phase 2: The Wiki Engine"
            subtitle="Connecting the code to the planning documents."
            variant="alt"
          >
            <div className="grid two">
              <div className="card">
                <h3>Rendering Engine</h3>
                <p>Jinja2 integration for processing Markdown templates.</p>
              </div>
              <div className="card">
                <h3>Template Context</h3>
                <p>Exposing the issue graph (counts, status, lists) to the template context.</p>
              </div>
            </div>
          </Section>

          <Section
            title="Phase 3: Polish & Release"
            subtitle="Refining the experience for daily use."
          >
            <div className="grid two">
              <div className="card">
                <h3>Search</h3>
                <p>Full-text search across issues and comments.</p>
              </div>
              <div className="card">
                <h3>Validation</h3>
                <p>Strict schema validation and graph integrity checks (orphaned dependencies).</p>
              </div>
              <div className="card">
                <h3>Statistics</h3>
                <p>Burndown charts and velocity metrics generated from history.</p>
              </div>
              <div className="card">
                <h3>IDE Integration</h3>
                <p>VS Code extension for highlighting and auto-complete.</p>
              </div>
            </div>
          </Section>
        </div>
      </div>
    </Layout>
  );
};

export default RoadmapPage;
