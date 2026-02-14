import * as React from "react";

type CodeBlockProps = {
  children: string;
  label?: string;
};

const CodeBlock = ({ children, label }: CodeBlockProps) => {
  const [copied, setCopied] = React.useState(false);
  const timeoutRef = React.useRef<number | null>(null);

  React.useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const handleCopy = async () => {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
    }
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(children);
      } else {
        const textarea = document.createElement("textarea");
        textarea.value = children;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        document.body.removeChild(textarea);
      }
      setCopied(true);
      timeoutRef.current = window.setTimeout(() => {
        setCopied(false);
      }, 1500);
    } catch (error) {
      setCopied(false);
    }
  };

  return (
    <div className="relative">
      {label ? (
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          {label}
        </div>
      ) : null}
      <button
        type="button"
        onClick={handleCopy}
        className="absolute right-3 top-3 rounded-md border border-slate-200 bg-white/90 px-2.5 py-1 text-xs font-medium text-slate-600 hover:text-slate-900 hover:border-slate-300 transition-colors dark:border-slate-700 dark:bg-slate-900/90 dark:text-slate-300 dark:hover:text-white dark:hover:border-slate-500"
      >
        {copied ? "Copied" : "Copy"}
      </button>
      <pre className="block overflow-x-auto rounded-xl bg-slate-100 dark:bg-slate-800 p-6 text-sm text-slate-800 dark:text-slate-200 font-mono leading-relaxed border border-slate-200 dark:border-slate-700">
        {children}
      </pre>
    </div>
  );
};

export default CodeBlock;
