import * as React from "react";
import { Copy, Check } from "lucide-react";

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

  const renderHighlighted = (code: string) => {
    // Simple regex-based highlighter for our documentation blocks
    // This isn't perfect but handles our shell scripts, YAML, and Gherkin reasonably well
    const html = code
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      // Comments
      .replace(/^(#.*)$/gm, '<span class="text-muted opacity-70">$1</span>')
      // Shell commands
      .replace(/^(\$\s+)?(kanbus|kbs)(\s)/gm, '<span class="text-muted opacity-50">$1</span><span class="text-sky-400 font-bold">$2</span>$3')
      // Feature / Scenario / Given / When / Then (Gherkin)
      .replace(/^(Feature|Scenario|Given|When|Then|And|But)(:?)/gm, '<span class="text-indigo-400 font-bold">$1</span>$2')
      // JSON keys
      .replace(/"([^"]+)":/g, '<span class="text-sky-400">"$1"</span>:')
      // Flags (e.g. --status)
      .replace(/(--\w+[\w-]*)/g, '<span class="text-pink-400">$1</span>')
      // Quoted strings
      .replace(/("[^"]*")/g, '<span class="text-green-400">$1</span>');
      
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
  };

  return (
    <div className="rounded-xl overflow-hidden flex flex-col bg-background border border-border/50 hover:border-selected/30 hover:shadow-[0_0_15px_var(--glow-center)] transition-all duration-300">
      <div className="flex items-center justify-between px-4 py-2 bg-column border-b border-border/50">
        <div className="text-xs font-mono text-muted uppercase tracking-wider">
          {label || ""}
        </div>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium text-muted hover:text-foreground hover:bg-card-muted transition-colors"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5" />
              Copied
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              Copy
            </>
          )}
        </button>
      </div>
      <pre className="block overflow-x-auto p-4 md:p-6 text-sm text-foreground font-mono leading-relaxed">
        {renderHighlighted(children)}
      </pre>
    </div>
  );
};

export { CodeBlock }
