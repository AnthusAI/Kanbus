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
    const lines = code.split("\n");
    return (
      <code className="block">
        {lines.map((line, lineIndex) => {
          const key = `line-${lineIndex}`;
          if (/^#/.test(line)) {
            return (
              <span key={key} className="text-muted opacity-70">
                {line}
                {"\n"}
              </span>
            );
          }
          const gherkinMatch = line.match(/^(Feature|Scenario|Given|When|Then|And|But)(:?)(.*)$/);
          if (gherkinMatch) {
            const [, keyword, colon, rest] = gherkinMatch;
            return (
              <span key={key}>
                <span className="text-indigo-400 font-bold">{keyword}</span>
                {colon}
                {highlightRest(rest, key)}
                {"\n"}
              </span>
            );
          }
          const parts: React.ReactNode[] = [];
          const promptMatch = line.match(/^(\$\s+)?(kanbus|kbs)(\s)/);
          let rest = line;
          if (promptMatch) {
            const [full, prompt = "", command, space] = promptMatch;
            if (prompt) {
              parts.push(
                <span key={`${key}-prompt`} className="text-muted opacity-50">
                  {prompt}
                </span>
              );
            }
            parts.push(
              <span key={`${key}-cmd`} className="text-sky-400 font-bold">
                {command}
              </span>
            );
            parts.push(space);
            rest = line.slice(full.length);
          }
          parts.push(highlightRest(rest, key));
          return (
            <span key={key}>
              {parts}
              {"\n"}
            </span>
          );
        })}
      </code>
    );
  };

  const highlightRest = (rest: string, lineKey: string): React.ReactNode[] => {
    const parts: React.ReactNode[] = [];
    const regex = /(--\w+[\w-]*)|("[^"]*")|("([^"]+)":)/g;
    let lastEnd = 0;
    let match;
    while ((match = regex.exec(rest)) !== null) {
      if (match.index > lastEnd) {
        parts.push(rest.slice(lastEnd, match.index));
      }
      if (match[1]) {
        parts.push(
          <span key={`${lineKey}-flag-${match.index}`} className="text-pink-400">
            {match[1]}
          </span>
        );
      } else if (match[2] && !match[4]) {
        parts.push(
          <span key={`${lineKey}-str-${match.index}`} className="text-green-400">
            {match[2]}
          </span>
        );
      } else if (match[3]) {
        parts.push(
          <span key={`${lineKey}-json-${match.index}`} className="text-sky-400">
            &quot;{match[4]}&quot;
          </span>
        );
        parts.push(":");
      }
      lastEnd = regex.lastIndex;
    }
    if (lastEnd < rest.length) {
      parts.push(rest.slice(lastEnd));
    }
    return parts;
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
