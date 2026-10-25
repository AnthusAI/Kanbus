import React from "react";
import {
  BarChart3,
  Clock,
  FileText,
  LayoutGrid,
  Layers,
  Lightbulb,
  ListChecks,
  SquareCheckBig,
} from "lucide-react";
import type { SelectorOption } from "@kanbus/ui";

type SelectorIcon = React.ComponentType<{ className?: string }>;

function buildSelectorOption(id: string, label: string, icon: SelectorIcon): SelectorOption {
  return {
    id,
    label,
    content: (
      <span className="selector-option">
        {React.createElement(icon, { className: "h-4 w-4" })}
        <span className="selector-label">{label}</span>
      </span>
    )
  };
}

export function buildTypeFilterOptions(showInitiatives: boolean): SelectorOption[] {
  const options: SelectorOption[] = [];
  options.push(buildSelectorOption("all", "All", Layers));
  if (showInitiatives) {
    options.push(buildSelectorOption("initiatives", "Initiatives", Lightbulb));
  }
  options.push(buildSelectorOption("epics", "Epics", ListChecks));
  options.push(buildSelectorOption("issues", "Issues", SquareCheckBig));
  return options;
}

export function buildPanelModeOptions(): SelectorOption[] {
  return [
    buildSelectorOption("now", "Now", Clock),
    buildSelectorOption("board", "Board", LayoutGrid),
    buildSelectorOption("wiki", "Wiki", FileText),
    buildSelectorOption("metrics", "Metrics", BarChart3)
  ];
}
