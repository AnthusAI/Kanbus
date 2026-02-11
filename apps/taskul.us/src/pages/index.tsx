import * as React from "react";
import type { PageProps } from "gatsby";
import { Hero, Layout } from "../components";
import "../styles/content.css";
import { referenceProjects } from "../lib/reference";

const IndexPage: React.FC<PageProps> = () => {
  return (
    <Layout>
      <Hero
        title="Taskulus public website scaffold"
        subtitle="Minimal Gatsby 5 + Tailwind CSS project that mirrors the VideoML reference structure and is ready for AWS Amplify Gen 2 deployment."
        actions={
          <>
            <a
              href="https://docs.aws.amazon.com/amplify/latest/userguide/welcome.html"
              className="rounded-full bg-[var(--primary)] px-6 py-2 text-sm font-semibold text-white shadow-lg shadow-blue-500/20"
              target="_blank"
              rel="noreferrer"
            >
              Amplify deployment guide
            </a>
            <a
              href="https://github.com/AnthusAI/Taskulus"
              className="rounded-full border border-white/20 px-6 py-2 text-sm font-semibold text-white/80"
              target="_blank"
              rel="noreferrer"
            >
              Taskulus on GitHub
            </a>
          </>
        }
      />

      <section className="content-shell">
        <h2>Project status</h2>
        <p>
          This repository only includes the foundational Gatsby application.
          Content design, authoring, and deployment tasks are tracked in Beads
          epic <code>tskl-0lb</code>. Clone this structure, customize the
          components, and push to AWS Amplify Gen 2 for live hosting.
        </p>
      </section>

      <section className="content-shell">
        <h2>Reference implementation</h2>
        <p>
          Agents working on this project should inspect the VideoML site to
          understand the intended architecture and component breakdown. The path
          on this workstation is listed below:
        </p>
        <ul className="mt-6 space-y-4 rounded-xl border border-white/10 bg-white/5 p-6 text-left text-sm text-slate-200">
          {referenceProjects.map((project) => (
            <li key={project.path}>
              <p className="font-mono text-xs text-slate-400">
                {project.path}
              </p>
              <p className="mt-1 text-base text-white">{project.label}</p>
              <p className="text-slate-400">{project.description}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="content-shell">
        <h2>Next steps</h2>
        <ol className="list-decimal space-y-2 pl-4 text-slate-300">
          <li>Design the visual system and IA for taskul.us.</li>
          <li>Author marketing copy, documentation highlights, and CTAs.</li>
          <li>Wire Amplify build settings to this folder: <code>apps/taskul.us</code>.</li>
          <li>Provision Route 53 hosted zone and attach GoDaddy name servers.</li>
          <li>Connect the custom domain inside Amplify and verify SSL.</li>
        </ol>
      </section>
    </Layout>
  );
};

export default IndexPage;

export const Head = () => (
  <>
    <title>Taskulus public website</title>
    <meta
      name="description"
      content="Base Gatsby site for the Taskulus public website running on AWS Amplify Gen 2."
    />
  </>
);
