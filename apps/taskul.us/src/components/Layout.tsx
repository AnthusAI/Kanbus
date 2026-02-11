import * as React from "react";

const navigation = [
  { label: "Philosophy", href: "/philosophy" },
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
        <div className="container">
           <nav className="nav">
             <a href="/" className="brand">Taskulus</a>
             <div className="nav-links">
               {navigation.map((item) => (
                 <a key={item.href} href={item.href}>{item.label}</a>
               ))}
             </div>
           </nav>
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
