import * as React from "react";

const navigation = [
  { label: "Product", href: "/product" },
  { label: "Docs", href: "/docs" },
  { label: "Roadmap", href: "/roadmap" },
];

type LayoutProps = {
  children: React.ReactNode;
};

const Layout = ({ children }: LayoutProps) => {
  return (
    <div>
      <header className="page">
        <div className="container hero">
          <div>
            <span className="pill">Taskulus</span>
            <h1 className="hero-title">Git-native project management.</h1>
            <p className="hero-subtitle">
              A file-based tracker with a shared specification, dual Python and
              Rust implementations, and planning documents that stay in sync.
            </p>
            <div className="hero-actions">
              <a className="button" href="/docs">
                Read the docs
              </a>
              <a className="button secondary" href="/product">
                See the product
              </a>
            </div>
          </div>
          <div className="section alt">
            <p className="pill">Now</p>
            <h2>Planning phase</h2>
            <p>
              Taskulus is being built in the open with behavior-driven
              specifications and shared fixtures. Follow along and help shape
              the first release.
            </p>
            <div className="grid two">
              <div className="card">
                <h3>Shared specs</h3>
                <p>One Gherkin suite drives both implementations.</p>
              </div>
              <div className="card">
                <h3>Local files</h3>
                <p>Issues live as readable JSON in your repository.</p>
              </div>
            </div>
          </div>
        </div>
      </header>
      <main>{children}</main>
      <footer className="footer">
        <div className="container split">
          <div>
            <h4>Taskulus</h4>
            <p>Git-backed project management system.</p>
          </div>
          <div>
            <h4>Explore</h4>
            <p>
              <a href="/docs">Documentation</a>
            </p>
            <p>
              <a href="/roadmap">Roadmap</a>
            </p>
          </div>
          <div>
            <h4>Community</h4>
            <p>
              <a href="https://github.com/AnthusAI/Taskulus">GitHub</a>
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Layout;
