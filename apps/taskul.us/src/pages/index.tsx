import * as React from "react";
import { Layout, Section, Hero } from "../components";

const IndexPage = () => {
  return (
    <Layout>
      <div className="page">
        <div className="container">
          <Hero
            title="Git-backed project management"
            subtitle="Files are the database. Taskulus keeps your issues, plans, and code in one repository."
            eyebrow="Taskulus"
            actions={
              <>
                <a className="button" href="/docs">
                  Get Started
                </a>
                <a className="button secondary" href="/philosophy">
                  Learn More
                </a>
              </>
            }
          />
        </div>
        
        <div className="container grid">
          <Section
            title="Files are the database"
            subtitle="Stop syncing your work to a separate silo. Taskulus stores everything in your Git repository."
          >
            <div className="grid two">
              <div className="card">
                <h3>JSON Issues</h3>
                <p>Every issue is a single JSON file. Branch, merge, and review issues just like code.</p>
              </div>
              <div className="card">
                <h3>No Merge Conflicts</h3>
                <p>Designed with a minimum-schema format that avoids conflicts even on active teams.</p>
              </div>
            </div>
          </Section>

          <Section
            title="Integrated Wiki"
            subtitle="The forest vs the trees. Live planning documents that render real-time issue data."
            variant="alt"
          >
            <div className="grid two">
              <div className="card">
                <h3>Live Data</h3>
                <p>Use Jinja2 templates to pull live issue counts, status, and lists into your planning docs.</p>
              </div>
              <div className="card">
                <h3>Versioned Plans</h3>
                <p>Your specifications evolve with your code. Go back in time and see exactly what was planned.</p>
              </div>
            </div>
          </Section>

          <Section
            title="Dual Implementation"
            subtitle="One behavior specification driving two complete implementations."
          >
            <div className="grid two">
              <div className="card">
                <h3>Python</h3>
                <p>Easy to install, easy to extend. Perfect for scripting and local workflows.</p>
              </div>
              <div className="card">
                <h3>Rust</h3>
                <p>High-performance backend for CI/CD pipelines and large repositories.</p>
              </div>
            </div>
          </Section>

          <Section
            title="Why Taskulus?"
            subtitle="Built for developers who want to own their data."
            variant="alt"
          >
             <div className="grid three">
              <div className="card">
                <h3>Vs. Beads</h3>
                <p>Taskulus is a spiritual successor to Beads, focusing on simplicity and removing complex graph requirements.</p>
              </div>
              <div className="card">
                <h3>Vs. Jira</h3>
                <p>No slow web UI. No separate login. No downtime. Your data is always on your disk.</p>
              </div>
              <div className="card">
                <h3>Vs. Markdown</h3>
                <p>Structured data where you need it (status, priority), free text where you want it (description).</p>
              </div>
            </div>
          </Section>
        </div>
      </div>
    </Layout>
  );
};

export default IndexPage;
