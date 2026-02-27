import * as React from "react";
import { Link } from "gatsby";
import { DocsLayout } from "../../components";
import { PageProps } from "gatsby";

const DocsIndexPage = ({ location }: PageProps) => {
  return (
    <DocsLayout currentPath={location.pathname}>
      <div className="space-y-8">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground tracking-tight">Overview</h1>
          <p className="mt-4 text-xl text-muted leading-relaxed">
            Everything you need to know about the Kanbus file structure and CLI.
          </p>
        </div>

        <div className="mt-6">
          <Link to="/features" className="text-muted hover:text-foreground transition-colors inline-flex items-center gap-1">
            ← Back to Features
          </Link>
        </div>
        
        <div className="prose prose-slate dark:prose-invert max-w-none text-muted leading-relaxed">
          <p>
            Kanbus is a Git-backed project management system. Instead of storing your issues, 
            epics, and tasks in a remote database, Kanbus stores them as JSON files directly in your 
            repository. This means your project management stays perfectly in sync with your code.
          </p>
          
          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Getting Started
          </h2>
          <p>
            The easiest way to understand Kanbus is to explore its components. Use the sidebar to 
            navigate through the documentation:
          </p>
          <ul className="list-disc pl-5 space-y-2 mt-4">
            <li>
              <strong>CLI Reference:</strong> Learn about the core commands and workflow tools 
              that make up the Kanbus interface.
            </li>
            <li>
              <strong>Configuration:</strong> Understand how to customize Kanbus, define 
              your issue hierarchy, and set up your workflow states.
            </li>
            <li>
              <strong>Directory Structure:</strong> See how Kanbus organizes files within 
              your repository's <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">project/</code> directory.
            </li>
          </ul>
        </div>
      </div>
    </DocsLayout>
  );
};

export default DocsIndexPage;
