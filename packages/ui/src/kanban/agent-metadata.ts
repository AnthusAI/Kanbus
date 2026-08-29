export type AgentSettings = Record<string, unknown>;

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

function formatSettingValue(value: unknown): string {
  if (value === null) {
    return "null";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

export function formatAgentSettingsDisplay(
  metadata: AgentMetadata
): string | null {
  const settings = metadata.settings;
  if (!settings || Object.keys(settings).length === 0) {
    return null;
  }
  const parts = Object.entries(settings)
    .sort(([leftKey], [rightKey]) => leftKey.localeCompare(rightKey))
    .map(([key, value]) => `${key}=${formatSettingValue(value)}`);
  return parts.join(", ");
}
