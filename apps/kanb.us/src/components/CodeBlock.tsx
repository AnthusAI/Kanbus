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

  return (
    <div className="rounded-xl overflow-hidden flex flex-col bg-background">
      <div className="flex items-center justify-between px-4 py-2 bg-column">
        <div className="text-xs font-mono text-muted uppercase tracking-wider">
          {label || ""}
        </div>
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium text-muted hover:text-foreground hover:bg-card transition-colors"
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
        {children}
      </pre>
    </div>
  );
};

export default CodeBlock;
