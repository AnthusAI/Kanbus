import React, { useLayoutEffect, useMemo, useRef, useState } from "react";
import { Group } from "@visx/group";
import { BarStackHorizontal } from "@visx/shape";
import { scaleBand, scaleLinear } from "@visx/scale";
import type { Issue, ProjectConfig } from "../types/issues";
import { buildStatusCategoryColorVariable } from "../utils/issue-colors";

interface MetricsPanelProps {
  issues: Issue[];
  config: ProjectConfig;
  hasVirtualProjects: boolean;
  hasLocalIssues: boolean;
  projectLabels: string[];
}

interface MetricsStatusRow {
  key: string;
  label: string;
  count: number;
}

interface MetricsLabelCount {
  label: string;
  count: number;
}

interface MetricsChartDatum {
  type: string;
  total: number;
  [key: string]: number | string;
}

interface MetricsLegendEntry {
  label: string;
  color: string;
}

const CHART_COLOR_SCALE = "6";
const FALLBACK_COLOR = "var(--slate-6)";

function formatTypeLabel(value: string): string {
  return value
    .split("-")
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(" ");
}

function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    const node = ref.current;
    if (!node) {
      return;
    }
    const update = () => {
      const rect = node.getBoundingClientRect();
      setSize({ width: rect.width, height: rect.height });
    };
    update();
    if (typeof ResizeObserver === "undefined") {
      return;
    }
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return { ref, width: size.width, height: size.height };
}

function resolveIssueProjectLabel(issue: Issue, config: ProjectConfig): string {
  return (issue.custom?.project_label as string) || config.project_key;
}

function resolveIssueScope(issue: Issue): "local" | "project" {
  return issue.custom?.source === "local" ? "local" : "project";
}

function buildMetricsSummary(
  issues: Issue[],
  config: ProjectConfig,
  projectLabels: string[]
): {
  total: number;
  statusRows: MetricsStatusRow[];
  projectRows: MetricsLabelCount[];
  scopeRows: MetricsLabelCount[];
} {
  const total = issues.length;
  const statusCounts: Record<string, number> = {};
  const projectCounts: Record<string, number> = {};
  let localCount = 0;
  let projectCount = 0;

  issues.forEach((issue) => {
    statusCounts[issue.status] = (statusCounts[issue.status] ?? 0) + 1;
    const label = resolveIssueProjectLabel(issue, config);
    projectCounts[label] = (projectCounts[label] ?? 0) + 1;
    if (resolveIssueScope(issue) === "local") {
      localCount += 1;
    } else {
      projectCount += 1;
    }
  });

  const statusRows = config.statuses.map((status) => ({
    key: status.key,
    label: status.name,
    count: statusCounts[status.key] ?? 0,
  }));

  const projectRows = projectLabels.map((label) => ({
    label,
    count: projectCounts[label] ?? 0,
  }));

  const scopeRows = [
    { label: "Project", count: projectCount },
    { label: "Local", count: localCount },
  ];

  return { total, statusRows, projectRows, scopeRows };
}

function buildTypeOrder(config: ProjectConfig): string[] {
  const order = [...config.hierarchy, ...config.types];
  const seen = new Set<string>();
  return order.filter((value) => {
    if (seen.has(value)) {
      return false;
    }
    seen.add(value);
    return true;
  });
}

function buildChartData(
  issues: Issue[],
  config: ProjectConfig
): {
  data: MetricsChartDatum[];
  statusKeys: string[];
  statusColors: Record<string, string>;
  legend: MetricsLegendEntry[];
} {
  const statusKeys = config.statuses.map((status) => status.key);
  const typeOrder = buildTypeOrder(config);
  const typeCounts: Record<string, Record<string, number>> = {};
  const statusCategoryNames: Record<string, string | null> = {};

  issues.forEach((issue) => {
    if (!typeCounts[issue.type]) {
      typeCounts[issue.type] = {};
    }
    typeCounts[issue.type][issue.status] =
      (typeCounts[issue.type][issue.status] ?? 0) + 1;
  });

  const data = typeOrder
    .filter((type) => typeCounts[type])
    .map((type) => {
      const entry: MetricsChartDatum = {
        type,
        total: 0,
      };
      statusKeys.forEach((status) => {
        const count = typeCounts[type][status] ?? 0;
        entry[status] = count;
        entry.total += count;
      });
      return entry;
    })
    .filter((entry) => entry.total > 0);

  const statusColors: Record<string, string> = {};
  const legendMap: Record<string, MetricsLegendEntry> = {};

  config.statuses.forEach((status) => {
    const color = buildStatusCategoryColorVariable(
      config,
      status.key,
      CHART_COLOR_SCALE
    );
    statusColors[status.key] = color ?? FALLBACK_COLOR;
    const category = config.categories.find(
      (item) => item.name === status.category
    );
    statusCategoryNames[status.key] = category?.name ?? null;
    if (category?.color) {
      const entryColor = color ?? FALLBACK_COLOR;
      if (!legendMap[category.name]) {
        legendMap[category.name] = {
          label: category.name,
          color: entryColor,
        };
      }
    }
  });

  const legend = Object.values(legendMap);
  if (!legend.length) {
    const fallback = new Set<string>();
    config.statuses.forEach((status) => {
      if (statusCategoryNames[status.key]) {
        fallback.add(statusCategoryNames[status.key] as string);
      }
    });
    fallback.forEach((category) => {
      legend.push({ label: category, color: FALLBACK_COLOR });
    });
  }

  return { data, statusKeys, statusColors, legend };
}

function MetricsChart({
  data,
  statusKeys,
  statusColors,
}: {
  data: MetricsChartDatum[];
  statusKeys: string[];
  statusColors: Record<string, string>;
}) {
  const { ref, width, height } = useElementSize<HTMLDivElement>();
  const margin = { top: 8, right: 16, bottom: 16, left: 120 };
  const minHeight = Math.max(220, data.length * 36 + margin.top + margin.bottom);
  const chartWidth = Math.max(width, 320);
  const chartHeight = Math.max(height, minHeight);

  if (!data.length) {
    return (
      <div ref={ref} className="metrics-chart-frame">
        <div className="metrics-empty">No data to chart</div>
      </div>
    );
  }

  const innerWidth = Math.max(0, chartWidth - margin.left - margin.right);
  const innerHeight = Math.max(0, chartHeight - margin.top - margin.bottom);
  const totals = data.map((row) => row.total as number);
  const maxTotal = totals.length ? Math.max(...totals) : 0;

  const yScale = scaleBand<string>({
    domain: data.map((row) => row.type),
    range: [0, innerHeight],
    padding: 0.2,
  });
  const xScale = scaleLinear<number>({
    domain: [0, maxTotal],
    range: [0, innerWidth],
    nice: true,
  });

  return (
    <div ref={ref} className="metrics-chart-frame">
      <svg width={chartWidth} height={chartHeight} role="img">
        <Group top={margin.top} left={margin.left}>
          <BarStackHorizontal
            data={data}
            keys={statusKeys}
            height={innerHeight}
            y={(row) => row.type}
            yScale={yScale}
            xScale={xScale}
            color={(key) => statusColors[key] ?? FALLBACK_COLOR}
          >
            {(barStacks) =>
              barStacks.map((barStack) =>
                barStack.bars.map((bar) => (
                  <rect
                    key={`${barStack.key}-${bar.index}`}
                    x={bar.x}
                    y={bar.y}
                    width={bar.width}
                    height={bar.height}
                    fill={bar.color}
                    rx={6}
                    className="visx-bar-group"
                    data-type={(bar.bar as any)?.data?.type ?? (bar as any)?.bar?.data?.type}
                  />
                ))
              )
            }
          </BarStackHorizontal>
          {data.map((row) => {
            const y = yScale(row.type);
            if (y == null) {
              return null;
            }
            return (
              <text
                key={row.type}
                x={-8}
                y={y + yScale.bandwidth() / 2}
                textAnchor="end"
                dominantBaseline="middle"
                className="metrics-axis-label"
              >
                {formatTypeLabel(row.type)}
              </text>
            );
          })}
        </Group>
      </svg>
    </div>
  );
}

export function MetricsPanel({
  issues,
  config,
  hasVirtualProjects,
  hasLocalIssues,
  projectLabels,
}: MetricsPanelProps) {
  const summary = useMemo(
    () => buildMetricsSummary(issues, config, projectLabels),
    [issues, config, projectLabels]
  );
  const chart = useMemo(() => buildChartData(issues, config), [issues, config]);

  return (
    <div className="metrics-panel">
      <div className="metrics-grid">
        <div className="metrics-summary">
          <div className="metrics-block">
            <div className="metrics-section-title">Total Issues</div>
            <div className="metrics-total" data-testid="metrics-total-count">
              {summary.total}
            </div>
          </div>
          <div className="metrics-block">
            <div className="metrics-section-title">Status</div>
            <div className="metrics-rows">
              {summary.statusRows.map((row) => (
                <div key={row.key} className="metrics-row">
                  <span className="metrics-row-label">{row.label}</span>
                  <span
                    className="metrics-row-value"
                    data-testid={`metrics-status-${row.key}`}
                  >
                    {row.count}
                  </span>
                </div>
              ))}
            </div>
          </div>
          {hasVirtualProjects ? (
            <div className="metrics-block">
              <div className="metrics-section-title">Project</div>
              <div className="metrics-rows">
                {summary.projectRows.map((row) => (
                  <div key={row.label} className="metrics-row">
                    <span className="metrics-row-label">{row.label}</span>
                    <span
                      className="metrics-row-value"
                      data-testid={`metrics-project-${row.label}`}
                    >
                      {row.count}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
          {hasLocalIssues ? (
            <div className="metrics-block">
              <div className="metrics-section-title">Scope</div>
              <div className="metrics-rows">
                {summary.scopeRows.map((row) => (
                  <div key={row.label} className="metrics-row">
                    <span className="metrics-row-label">{row.label}</span>
                    <span
                      className="metrics-row-value"
                      data-testid={`metrics-scope-${row.label.toLowerCase()}`}
                    >
                      {row.count}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
        <div className="metrics-chart">
          <div className="metrics-chart-header">
            <div className="metrics-section-title">Issues by Type</div>
          </div>
          <div className="metrics-chart-body">
            <MetricsChart
              data={chart.data}
              statusKeys={chart.statusKeys}
              statusColors={chart.statusColors}
            />
          </div>
          <div className="metrics-legend" data-testid="metrics-chart-legend">
            {chart.legend.map((entry) => (
              <div key={entry.label} className="metrics-legend-item">
                <span
                  className="metrics-legend-swatch"
                  style={{ background: entry.color }}
                />
                <span className="metrics-legend-label">{entry.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
