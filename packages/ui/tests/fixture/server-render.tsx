import React from "react";
import { renderToString } from "react-dom/server";
import { fixtureConfiguration, fixtureIssues } from "./fixture-data";
import { StackedBoardHost, buildStackedIssues, type StackedBoardSettings } from "./stacked-board-host";

export function renderStackedBoardMarkupOnServer(settings: StackedBoardSettings): string {
  return renderToString(
    <StackedBoardHost settings={settings} records={buildStackedIssues("articles", fixtureIssues)}
      baseConfiguration={fixtureConfiguration} />
  );
}
