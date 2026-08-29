export interface AgentSettings {
  temperature?: number;
  thinking_level?: "off" | "low" | "medium" | "high";
  max_output_tokens?: number;
}

export interface AgentMetadata {
  platform: string;
  model: string;
  settings?: AgentSettings;
}

export function hasAgentMetadata(
  metadata?: AgentMetadata | null
): metadata is AgentMetadata {
  if (!metadata) {
    return false;
  }
  return Boolean(metadata.platform?.trim() || metadata.model?.trim());
}

export function formatAgentDisplayLine(metadata: AgentMetadata): string {
  return `${metadata.platform} / ${metadata.model}`;
}

export function formatAgentSettingsDisplay(
  metadata: AgentMetadata
): string | null {
  const settings = metadata.settings;
  if (!settings) {
    return null;
  }
  const parts: string[] = [];
  if (settings.temperature !== undefined) {
    parts.push(`temperature=${settings.temperature}`);
  }
  if (settings.thinking_level) {
    parts.push(`thinking_level=${settings.thinking_level}`);
  }
  if (settings.max_output_tokens !== undefined) {
    parts.push(`max_output_tokens=${settings.max_output_tokens}`);
  }
  return parts.length > 0 ? parts.join(", ") : null;
}
