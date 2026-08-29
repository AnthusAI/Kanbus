export interface AgentSettings {
  temperature?: number;
  thinking_level?: "off" | "low" | "medium" | "high";
  max_output_tokens?: number;
  speed?: "normal" | "fast";
}

export interface AgentMetadata {
  platform: string;
  model: string;
  name?: string;
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
  const platformModel = `${metadata.platform} / ${metadata.model}`;
  if (metadata.name?.trim()) {
    return `${metadata.name} / ${platformModel}`;
  }
  return platformModel;
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
  if (settings.speed) {
    parts.push(`speed=${settings.speed}`);
  }
  return parts.length > 0 ? parts.join(", ") : null;
}
