import {
  formatAgentDisplayLine,
  formatAgentSettingsDisplay,
  hasAgentMetadata,
  type AgentMetadata,
} from "./agent-metadata";

interface AgentMetadataBlockProps {
  metadata: AgentMetadata;
  variant: "issue" | "comment";
  testIdPrefix?: string;
}

export function AgentMetadataBlock({
  metadata,
  variant,
  testIdPrefix,
}: AgentMetadataBlockProps) {
  if (!hasAgentMetadata(metadata)) {
    return null;
  }

  const prefix = testIdPrefix ?? (variant === "issue" ? "issue-agent" : "comment-agent");
  const settingsLine = formatAgentSettingsDisplay(metadata);
  const compact = variant === "comment" && !settingsLine;

  return (
    <section
      aria-label="Agent metadata"
      className={
        compact
          ? "agent-metadata-block rounded-xl bg-card-muted px-3 py-2 text-xs text-muted"
          : "agent-metadata-block rounded-xl bg-card-muted px-3 py-2 text-xs text-muted"
      }
      data-testid={`${prefix}-metadata`}
    >
      {compact ? (
        <div data-testid={`${prefix}-platform`}>{formatAgentDisplayLine(metadata)}</div>
      ) : (
        <dl className="grid gap-1">
          <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <dt className="font-semibold uppercase tracking-[0.2em]">Platform</dt>
            <dd data-testid={`${prefix}-platform`}>{metadata.platform}</dd>
            <dt className="font-semibold uppercase tracking-[0.2em]">Model</dt>
            <dd data-testid={`${prefix}-model`}>{metadata.model}</dd>
          </div>
          {settingsLine ? (
            <div className="grid grid-cols-[auto_1fr] gap-x-3">
              <dt className="font-semibold uppercase tracking-[0.2em]">Settings</dt>
              <dd data-testid={`${prefix}-settings`}>{settingsLine}</dd>
            </div>
          ) : null}
        </dl>
      )}
    </section>
  );
}
