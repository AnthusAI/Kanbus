import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { randomUUID } from "node:crypto";
import path from "node:path";

const targetDirectory = process.argv[2];
const issueCount = Number(process.argv[3] ?? "2000");

if (!targetDirectory) {
  console.error("usage: node generatePerformanceFixture.mjs <initialized-project-root> [issueCount]");
  process.exit(1);
}

const issuesDirectory = path.join(targetDirectory, "project", "issues");
rmSync(issuesDirectory, { recursive: true, force: true });
mkdirSync(issuesDirectory, { recursive: true });

const weightedTypes = [
  ["task", 50],
  ["epic", 15],
  ["sub-task", 15],
  ["bug", 8],
  ["story", 6],
  ["chore", 4],
  ["initiative", 2],
];
const weightedStatuses = [
  ["backlog", 20],
  ["open", 25],
  ["in_progress", 10],
  ["blocked", 5],
  ["closed", 40],
];

function pickWeighted(entries, ratio) {
  const total = entries.reduce((sum, entry) => sum + entry[1], 0);
  let threshold = ratio * total;
  for (const [value, weight] of entries) {
    threshold -= weight;
    if (threshold < 0) {
      return value;
    }
  }
  return entries[entries.length - 1][0];
}

const sentence =
  "The quick brown fox jumps over the lazy dog while the console renders another card with a realistic amount of descriptive text. ";

for (let index = 0; index < issueCount; index += 1) {
  const identifier = `kanbus-${randomUUID()}`;
  const createdAt = new Date(Date.UTC(2026, 0, 1) + index * 3_600_000).toISOString();
  const typeValue = pickWeighted(weightedTypes, ((index * 7919) % 1000) / 1000);
  const drawnStatus = pickWeighted(weightedStatuses, ((index * 104729) % 1000) / 1000);
  const statusValue =
    (typeValue === "epic" || typeValue === "initiative") && (drawnStatus === "backlog" || drawnStatus === "blocked")
      ? "open"
      : drawnStatus;
  const issue = {
    id: identifier,
    title: `Fixture issue ${index} ${"word ".repeat(index % 9)}`.trim(),
    description: sentence.repeat(1 + (index % 6)),
    type: typeValue,
    status: statusValue,
    priority: 1 + (index % 4),
    assignee: index % 3 === 0 ? "agent" : null,
    creator: null,
    parent: null,
    labels: [],
    dependencies: [],
    comments: [],
    created_at: createdAt,
    updated_at: createdAt,
    closed_at: statusValue === "closed" ? createdAt : null,
    right_now_summary: null,
    right_now_updated_at: null,
    custom: {},
  };
  writeFileSync(path.join(issuesDirectory, `${identifier}.json`), JSON.stringify(issue, null, 2));
}
console.log(`wrote ${issueCount} issues to ${issuesDirectory}`);
