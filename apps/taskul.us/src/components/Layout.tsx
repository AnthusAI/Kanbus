import * as React from "react";
import clsx from "clsx";

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
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-50 font-sans transition-colors duration-200">
      <header className="sticky top-0 z-50 w-full border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-950/80 backdrop-blur-md">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
           <nav className="flex items-center gap-8 w-full">
             <a href="/" className="text-xl font-heading font-bold tracking-tight text-slate-900 dark:text-white hover:text-primary-600 dark:hover:text-primary-400 transition-colors">
               Taskulus
             </a>
             <div className="flex items-center gap-6 ml-auto">
               {navigation.map((item) => (
                 <a key={item.href} href={item.href} className="hidden sm:block text-sm font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors">
                   {item.label}
                 </a>
               ))}
               <a href="https://github.com/AnthusAI/Taskulus" className="ml-4 text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors">
                  <span className="sr-only">GitHub</span>
                  <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
                  </svg>
               </a>
             </div>
           </nav>
        </div>
      </header>

      <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 md:py-12">
        {children}
      </main>

      <footer className="border-t border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 py-12 md:py-16">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            <div className="col-span-2 md:col-span-1">
              <span className="text-lg font-heading font-bold text-slate-900 dark:text-white">Taskulus</span>
              <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">
                Git-backed project management system. Files are the database.
              </p>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Explore</h4>
              <ul className="mt-4 space-y-3 text-sm">
                <li><a href="/docs" className="text-slate-500 dark:text-slate-400 hover:text-primary-600 dark:hover:text-primary-400">Documentation</a></li>
                <li><a href="/roadmap" className="text-slate-500 dark:text-slate-400 hover:text-primary-600 dark:hover:text-primary-400">Roadmap</a></li>
                <li><a href="/philosophy" className="text-slate-500 dark:text-slate-400 hover:text-primary-600 dark:hover:text-primary-400">Philosophy</a></li>
              </ul>
            </div>
            <div>
               <h4 className="text-sm font-semibold text-slate-900 dark:text-white">Community</h4>
               <ul className="mt-4 space-y-3 text-sm">
                <li><a href="https://github.com/AnthusAI/Taskulus" className="text-slate-500 dark:text-slate-400 hover:text-primary-600 dark:hover:text-primary-400">GitHub</a></li>
              </ul>
            </div>
          </div>
          <div className="mt-12 pt-8 border-t border-slate-200 dark:border-slate-800 text-sm text-slate-400 dark:text-slate-500">
             &copy; {new Date().getFullYear()} Taskulus. Open source software.
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Layout;
