import * as React from "react";
import { Link, PageProps } from "gatsby";
import { DocsLayout, CodeBlock } from "../../components";

const DocsAgentProvenancePage = ({ location }: PageProps) => {
  return (
    <DocsLayout currentPath={location.pathname}>
      <div className="space-y-8">
        <div>
          <h1 className="text-4xl font-display font-bold text-foreground tracking-tight">
            Agent provenance
          </h1>
          <p className="mt-4 text-xl text-muted leading-relaxed">
            Tag creates and comments with product, model, and session name so a
            multi-agent board stays readable.
          </p>
        </div>

        <div className="prose prose-slate max-w-none text-muted leading-relaxed space-y-6">
          <p>
            Kanbus does not read <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">.cursor</code>,{" "}
            <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">.claude</code>, or other
            host directories. Those files are for the agents that run in that product.
            The CLI only merges flags and <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">KANBUS_AGENT_*</code>{" "}
            environment variables.
          </p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Who owns what
          </h2>
          <ul className="list-disc pl-5 space-y-2">
            <li>
              <strong className="text-foreground">Host product config</strong> — identity for agents in that product: product name, and this session&apos;s model when you know it. Session name stays per-run.
            </li>
            <li>
              <strong className="text-foreground">CONTRIBUTING_AGENT.md</strong> — how to tag. Title Case names, flags, environment variables, the warning, and how to fill tags later.
            </li>
            <li>
              <strong className="text-foreground">AGENTS.md</strong> — pointer to CONTRIBUTING_AGENT.md only. Do not put product or model names there.
            </li>
            <li>
              <strong className="text-foreground">kbs / kanbus</strong> — if provenance is incomplete, the write still succeeds and stderr prints a one-step update command.{" "}
              <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">--no-agent-provenance</code>{" "}
              silences the warning.
            </li>
          </ul>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Names
          </h2>
          <p>
            Use Title Case product and model names. Preferred products: Cursor, Codex, Claude Code, Antigravity, Grok Bot.
            Example models: Composer 2.5, GPT-5.6, Claude Sonnet 4, Grok 4. Session name is this run or bot (for example Cloud Agent), not the product.
          </p>

          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            CLI
          </h2>
          <p>
            Prefer environment defaults when the host can set them. Still pass a session name:
          </p>
        </div>

        <CodeBlock>
{`export KANBUS_AGENT_PLATFORM="Cursor"
export KANBUS_AGENT_MODEL="Composer 2.5"

kbs comment kbs-abc "Progress: schema drafted" --agent-name "Cloud Agent"`}
        </CodeBlock>

        <div className="prose prose-slate max-w-none text-muted leading-relaxed space-y-4">
          <p>If the environment is not set, pass the names from the host instructions:</p>
        </div>

        <CodeBlock>
{`kbs create "Fix login" --type task \\
  --agent-platform "Cursor" \\
  --agent-model "Composer 2.5" \\
  --agent-name "Cloud Agent"`}
        </CodeBlock>

        <div className="prose prose-slate max-w-none text-muted leading-relaxed space-y-4">
          <p>
            If you omitted tags, copy the command from the warning. You do not need to rewrite the issue or comment text:
          </p>
        </div>

        <CodeBlock>
{`kbs update kbs-abc --agent-platform "Cursor" --agent-model "Composer 2.5" --agent-name "Cloud Agent"
kbs comment update kbs-abc <comment-id> --agent-platform "Cursor" --agent-model "Composer 2.5" --agent-name "Cloud Agent"`}
        </CodeBlock>

        <div className="prose prose-slate max-w-none text-muted leading-relaxed space-y-6">
          <h2 className="text-2xl font-display font-bold text-foreground tracking-tight mt-8 mb-4">
            Host identity snippets
          </h2>
          <p>
            Paste the matching block into that product&apos;s project instructions or rules. Do not put these strings in shared AGENTS.md.
            The model changes often: use the name the host shows for this session, or set{" "}
            <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">KANBUS_AGENT_MODEL</code>.
          </p>

          <h3 className="text-xl font-bold text-foreground mt-6">Cursor</h3>
          <p>
            Suggested location: a Cursor project rule (for example{" "}
            <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">.cursor/rules/kanbus-provenance.mdc</code>
            ). Cloud hosts can inject session environment instead. Those values are not credentials; use a secrets UI only if that is how the host exports environment variables.
          </p>
        </div>

        <CodeBlock>
{`When you create or comment on Kanbus issues, tag agent provenance.

Product: Cursor
Model: the model name for this session (Title Case, for example Composer 2.5)
Session name: a short label for this run (for example Cloud Agent)

If KANBUS_AGENT_PLATFORM and KANBUS_AGENT_MODEL are set, reuse them and still pass --agent-name.
Otherwise pass --agent-platform "Cursor" --agent-model "<this session>" --agent-name "<this run>".

If kbs warns that provenance is incomplete, copy the printed kbs update or kbs comment update command.
Read CONTRIBUTING_AGENT.md (Agent provenance metadata) for the procedure.`}
        </CodeBlock>

        <div className="prose prose-slate max-w-none text-muted leading-relaxed space-y-4">
          <h3 className="text-xl font-bold text-foreground mt-6">Claude Code</h3>
          <p>
            Suggested location: Claude Code project instructions under{" "}
            <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">.claude/</code>
            , not root AGENTS.md.
          </p>
        </div>

        <CodeBlock>
{`When you create or comment on Kanbus issues, tag agent provenance.

Product: Claude Code
Model: the model name for this session (Title Case, for example Claude Sonnet 4)
Session name: a short label for this run

If KANBUS_AGENT_PLATFORM and KANBUS_AGENT_MODEL are set, reuse them and still pass --agent-name.
Otherwise pass --agent-platform "Claude Code" --agent-model "<this session>" --agent-name "<this run>".

If kbs warns that provenance is incomplete, copy the printed update command.
Read CONTRIBUTING_AGENT.md (Agent provenance metadata).`}
        </CodeBlock>

        <div className="prose prose-slate max-w-none text-muted leading-relaxed space-y-4">
          <h3 className="text-xl font-bold text-foreground mt-6">Codex</h3>
          <p>Suggested location: Codex project instructions for this workspace, not shared AGENTS.md.</p>
        </div>

        <CodeBlock>
{`When you create or comment on Kanbus issues, tag agent provenance.

Product: Codex
Model: the model name for this session (Title Case, for example GPT-5.6)
Session name: a short label for this run

If KANBUS_AGENT_* defaults are set, reuse platform and model and still pass --agent-name.
Otherwise pass --agent-platform "Codex" --agent-model "<this session>" --agent-name "<this run>".

If kbs warns, copy the printed kbs update or kbs comment update command.
Read CONTRIBUTING_AGENT.md (Agent provenance metadata).`}
        </CodeBlock>

        <div className="prose prose-slate max-w-none text-muted leading-relaxed space-y-4">
          <h3 className="text-xl font-bold text-foreground mt-6">Antigravity</h3>
          <p>Suggested location: Antigravity project or agent instructions for this workspace.</p>
        </div>

        <CodeBlock>
{`When you create or comment on Kanbus issues, tag agent provenance.

Product: Antigravity
Model: the model name for this session (Title Case)
Session name: a short label for this run

Prefer KANBUS_AGENT_PLATFORM and KANBUS_AGENT_MODEL when set; still pass --agent-name.
Otherwise pass --agent-platform "Antigravity" --agent-model "<this session>" --agent-name "<this run>".

If kbs warns, copy the printed follow-up command.
Read CONTRIBUTING_AGENT.md (Agent provenance metadata).`}
        </CodeBlock>

        <div className="prose prose-slate max-w-none text-muted leading-relaxed space-y-4">
          <h3 className="text-xl font-bold text-foreground mt-6">Grok Bot</h3>
          <p>Suggested location: that bot or session&apos;s instructions, not shared AGENTS.md.</p>
        </div>

        <CodeBlock>
{`When you create or comment on Kanbus issues, tag agent provenance.

Product: Grok Bot
Model: the model name for this session (Title Case, for example Grok 4)
Session name: a short label for this bot or session

Prefer KANBUS_AGENT_* when set; still pass --agent-name.
Otherwise pass --agent-platform "Grok Bot" --agent-model "<this session>" --agent-name "<this run>".

If kbs warns, copy the printed kbs update or kbs comment update command.
Read CONTRIBUTING_AGENT.md (Agent provenance metadata).`}
        </CodeBlock>

        <p className="text-muted">
          Procedure for agents:{" "}
          <Link to="/docs/cli" className="text-selected font-semibold hover:underline">
            CLI Reference
          </Link>
          . In the repository, see{" "}
          <code className="rounded bg-card-muted px-1.5 py-0.5 text-xs font-medium text-foreground">
            docs/AGENT_PROVENANCE.md
          </code>{" "}
          and CONTRIBUTING_AGENT.md.
        </p>
      </div>
    </DocsLayout>
  );
};

export default DocsAgentProvenancePage;
