import React, { useMemo } from "react";
import { AnimatedSelector, type SelectorOption } from "./AnimatedSelector";
import type { KanbanConfig } from "../kanban/types";

export type IssueTypeConfiguration = Pick<KanbanConfig, "hierarchy" | "types">;

/** Independent types first, then hierarchy levels, preserving each configured order. */
export function getConfiguredIssueTypes(config: IssueTypeConfiguration): string[] {
  return [...new Set([...(config.types ?? []), ...(config.hierarchy ?? [])])];
}

/** Namespaced IDs keep real types distinct from console hierarchy views. */
export function getIssueTypeFilterOptions(config: IssueTypeConfiguration): SelectorOption[] {
  return getConfiguredIssueTypes(config).map((type) => ({
    id: `type:${type}`,
    label: type.replace(/[-_]/g, " ").replace(/^./, (letter) => letter.toUpperCase())
  }));
}

export function issueTypeFromFilter(value: string | null): string | undefined {
  return value?.startsWith("type:") ? value.slice(5) : undefined;
}

export interface IssueTypeFilterProps {
  config: IssueTypeConfiguration;
  value: string | null;
  onChange: (value: string) => void;
  /** Console hierarchy views can precede exact configured types. */
  viewOptions?: SelectorOption[];
  name?: string;
  className?: string;
}
const NO_VIEW_OPTIONS: SelectorOption[] = [];

/** The console's animated selector, shared with transport-free embedded hosts.
 * Selecting the active choice again clears to All. Labels remain readable;
 * a constrained host scrolls the choices rather than hiding configured types.
 */
export function IssueTypeFilter({ config, value, onChange, viewOptions = NO_VIEW_OPTIONS,
  name = "Issue type", className = "" }: IssueTypeFilterProps) {
  const options = useMemo(() => [
    { id: "all", label: "All" },
    ...viewOptions.filter((option) => option.id !== "all"),
    ...getIssueTypeFilterOptions(config)
  ], [config, viewOptions]);
  return (
    <div className={`kb-type-filter-scroll ${className}`}>
      <AnimatedSelector name={name} options={options} value={value ?? "all"}
        className="kb-type-filter"
        onChange={(next) => onChange(next === value ? "all" : next)} />
    </div>
  );
}
