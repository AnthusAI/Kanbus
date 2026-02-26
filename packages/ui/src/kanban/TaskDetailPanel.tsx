import React, { useEffect, useRef, useState } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";
import {
  X,
  CornerDownRight,
  Focus,
  Maximize
} from "lucide-react";
import gsap from "gsap";
import mermaid from "mermaid";
import plantumlEncoder from "plantuml-encoder";
import { Board } from "./Board";
import {
  buildIssueColorStyle,
  buildStatusBadgeStyle
} from "./issue-colors";
import { formatIssueId } from "./format-issue-id";
import { getTypeIcon } from "./issue-icons";
import type { KanbanConfig } from "./types";
import { formatTimestamp } from "./format-timestamp";
import { IconButton } from "./IconButton";
import { useFlashEffect } from "./useFlashEffect";
import { useTypingEffect } from "./useTypingEffect";

export type TaskDetailIssue = {
  id: string;
  title: string;
  description?: string;
  type: string;
  status: string;
  priority: number;
  assignee?: string;
  creator?: string;
  parent?: string;
  labels?: string[];
  dependencies?: IssueDependency[];
  comments?: IssueComment[];
  created_at?: string;
  updated_at?: string;
  closed_at?: string;
  custom?: Record<string, unknown>;
};

export type IssueEventType =
  | "issue_created"
  | "state_transition"
  | "field_updated"
  | "comment_added"
  | "comment_updated"
  | "comment_deleted"
  | "dependency_added"
  | "dependency_removed"
  | "issue_deleted"
  | "issue_localized"
  | "issue_promoted";

export type IssueEvent = {
  schema_version: number;
  event_id: string;
  issue_id: string;
  event_type: IssueEventType | string;
  occurred_at: string;
  actor_id: string;
  payload: Record<string, unknown>;
};

export type IssueEventsResponse = {
  issue_id: string;
  events: IssueEvent[];
  next_before?: string | null;
};

type IssueComment = {
  id?: string;
  author: string;
  text: string;
  created_at: string;
};

type IssueDependency = {
  issue_id: string;
  depends_on_id: string;
  type: string;
  created_at: string;
  created_by: string;
};

type TaskDetailConfig = KanbanConfig & { time_zone?: string | null };

async function fetchIssueEvents(
  apiBase: string,
  issueId: string,
  options?: { before?: string | null; limit?: number }
): Promise<IssueEventsResponse> {
  const params = new URLSearchParams();
  if (options?.limit) {
    params.set("limit", String(options.limit));
  }
  if (options?.before) {
    params.set("before", options.before);
  }
  const query = params.toString();
  const url = query
    ? `${apiBase}/issues/${issueId}/events?${query}`
    : `${apiBase}/issues/${issueId}/events`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`issue events request failed: ${response.status}`);
  }
  return (await response.json()) as IssueEventsResponse;
}

const markdownRenderer = new marked.Renderer();
markdownRenderer.link = (href: string, title: string | null | undefined, text: string) => {
  const safeTitle = title ? ` title="${title}"` : "";
  return `<a href="${href}"${safeTitle} target="_blank" rel="noopener noreferrer">${text}</a>`;
};
markdownRenderer.code = (code: string, infostring: string | undefined) => {
  if (infostring === "mermaid") {
    return `<div class="mermaid">${code}</div>`;
  }
  if (infostring === "plantuml") {
    const encoded = encodeURIComponent(code);
    return `<div class="plantuml-diagram" data-plantuml-source="${encoded}"></div>`;
  }
  if (infostring === "d2") {
    const encoded = encodeURIComponent(code);
    return `<div class="d2-diagram" data-d2-source="${encoded}"></div>`;
  }
  return `<pre><code class="language-${infostring || ""}">${code}</code></pre>`;
};

marked.setOptions({
  gfm: true,
  breaks: true,
  renderer: markdownRenderer
});

// Mermaid will be re-initialized with the current theme when rendering

interface TaskDetailPanelProps {
  task: TaskDetailIssue | null;
  allIssues: TaskDetailIssue[];
  columns: string[];
  priorityLookup: Record<number, string>;
  config?: TaskDetailConfig;
  apiBase: string;
  isOpen: boolean;
  isVisible: boolean;
  navDirection: "push" | "pop" | "none";
  widthPercent: number;
  layout?: "fixed" | "auto";
  onClose: () => void;
  onToggleMaximize: () => void;
  isMaximized: boolean;
  onAfterClose: () => void;
  onFocus: (issueId: string) => void;
  focusedIssueId: string | null;
  focusedCommentId?: string | null;
  onNavigateToDescendant?: (issue: TaskDetailIssue) => void;
}

interface DescendantLinkProps {
  issue: TaskDetailIssue;
  depth: number;
  priorityName: string;
  config?: TaskDetailConfig;
  onClick: () => void;
}

const DescendantLink = React.memo(({
  issue,
  depth,
  priorityName,
  config,
  onClick
}: DescendantLinkProps) => {
  const TypeIcon = getTypeIcon(issue.type, issue.status);
  const issueStyle = config ? buildIssueColorStyle(config, issue) : undefined;
  const statusLabel =
    config?.statuses.find((status) => status.key === issue.status)?.name ?? issue.status;
  const statusBadgeStyle = config ? buildStatusBadgeStyle(config, issue.status) : undefined;

  const handleClick = () => {
    onClick();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onClick();
    }
  };

  return (
    <div
      className="descendant-link issue-card w-full min-w-0 cursor-pointer rounded-lg hover:bg-card-muted transition-colors p-2"
      style={issueStyle}
      data-status={issue.status}
      data-type={issue.type}
      data-priority={priorityName}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      aria-label={`Navigate to ${formatIssueId(issue.id)}: ${issue.title}`}
    >
      <div className="flex flex-wrap items-start gap-2 min-w-0">
        <div className="flex min-w-0 flex-1 items-start gap-2">
          <div className="shrink-0" style={{ width: `${depth * 12}px` }} aria-hidden="true" />
          {depth > 0 ? (
            <CornerDownRight className="shrink-0 w-3 h-3 text-muted" aria-hidden="true" />
          ) : null}
          <TypeIcon className="issue-accent-icon w-4 h-4 shrink-0" aria-hidden="true" />
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="grid min-w-0 grid-cols-[auto,1fr] items-baseline gap-x-2 gap-y-1">
              <span className="issue-accent-id text-xs font-medium shrink-0">
                {formatIssueId(issue.id)}
              </span>
              <span className="text-sm text-foreground min-w-0 flex-1 break-words leading-snug">
                {issue.title}
              </span>
              <div className="col-start-2 flex flex-wrap items-start gap-2 sm:hidden">
                <span className="status-badge" style={statusBadgeStyle}>
                  {statusLabel}
                </span>
                <span className="issue-accent-priority">{priorityName}</span>
              </div>
            </div>
          </div>
        </div>
        <div className="hidden shrink-0 flex-wrap items-start justify-end gap-2 sm:flex sm:ml-auto">
          <span className="status-badge" style={statusBadgeStyle}>
            {statusLabel}
          </span>
          <span className="issue-accent-priority">{priorityName}</span>
        </div>
      </div>
    </div>
  );
});

DescendantLink.displayName = "DescendantLink";

export function TaskDetailPanel({
  task,
  allIssues,
  columns,
  priorityLookup,
  config,
  apiBase,
  isOpen,
  isVisible,
  navDirection,
  widthPercent,
  layout = "fixed",
  onClose,
  onToggleMaximize,
  isMaximized,
  onAfterClose,
  onFocus,
  focusedIssueId,
  focusedCommentId,
  onNavigateToDescendant
}: TaskDetailPanelProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const [displayTask, setDisplayTask] = useState<TaskDetailIssue | null>(task);
  const [outgoingTask, setOutgoingTask] = useState<TaskDetailIssue | null>(null);
  const [incomingTask, setIncomingTask] = useState<TaskDetailIssue | null>(null);
  const [pagePhase, setPagePhase] = useState<"idle" | "ready" | "animating">("idle");
  const [pageDirection, setPageDirection] = useState<"push" | "pop">("push");
  const [panelOpenActive, setPanelOpenActive] = useState(false);
  const [activeTab, setActiveTab] = useState<"comments" | "events">("comments");
  const [eventHistory, setEventHistory] = useState<IssueEvent[]>([]);
  const [eventCursor, setEventCursor] = useState<string | null>(null);
  const [eventLoading, setEventLoading] = useState(false);
  const [eventError, setEventError] = useState<string | null>(null);

  useEffect(() => {
    if (process.env.NODE_ENV === "production") return;
    console.log("[detail-panel] task", task?.id ?? null);
  }, [task?.id]);

  useEffect(() => {
    if (process.env.NODE_ENV === "production") return;
    const node = panelRef.current;
    if (!node) return;
    const id = window.requestAnimationFrame(() => {
      const rect = node.getBoundingClientRect();
      console.log("[detail-panel] rect", { width: rect.width, height: rect.height, layout });
    });
    return () => window.cancelAnimationFrame(id);
  }, [isVisible, task?.id, layout]);

  // Flash effects for real-time updates
  const statusFlashRef = useFlashEffect(task?.status, isOpen);
  const titleFlashRef = useFlashEffect(task?.title, isOpen);
  const descriptionFlashRef = useFlashEffect(task?.description, isOpen);

  // Typing effect for new descriptions
  const typedDescription = useTypingEffect(task?.description || "", isOpen && pagePhase !== "animating");

  // Track comment count to detect new comments
  const previousCommentCountRef = useRef<number>(0);

  // Auto-scroll to bottom when new comment is added to focused issue
  useEffect(() => {
    if (!task || !isOpen || !contentRef.current) return;

    const currentCommentCount = task.comments?.length || 0;

    // If comment count increased, scroll to bottom
    if (currentCommentCount > previousCommentCountRef.current && previousCommentCountRef.current > 0) {
      // Wait a brief moment for the comment to render, then scroll
      setTimeout(() => {
        if (contentRef.current) {
          contentRef.current.scrollTo({
            top: contentRef.current.scrollHeight,
            behavior: 'smooth'
          });
        }
      }, 100);
    }

    previousCommentCountRef.current = currentCommentCount;
  }, [task?.comments?.length, task, isOpen]);

  useEffect(() => {
    setActiveTab("comments");
    setEventHistory([]);
    setEventCursor(null);
    setEventError(null);
  }, [task?.id]);

  const loadEvents = async (reset: boolean) => {
    if (!task || !apiBase) {
      return;
    }
    if (eventLoading) {
      return;
    }
    setEventLoading(true);
    try {
      const response = await fetchIssueEvents(apiBase, task.id, {
        limit: 50,
        before: reset ? null : eventCursor
      });
      setEventHistory((current) =>
        reset ? response.events : [...current, ...response.events]
      );
      setEventCursor(response.next_before ?? null);
      setEventError(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to load events";
      setEventError(message);
    } finally {
      setEventLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab !== "events") {
      return;
    }
    if (!task || !apiBase) {
      return;
    }
    if (eventHistory.length > 0 || eventLoading) {
      return;
    }
    void loadEvents(true);
  }, [activeTab, task?.id, apiBase, eventHistory.length, eventLoading]);

  // Scroll to and highlight a specific comment — fires when the panel content
  // lands (displayTask?.id changes) or when focusedCommentId is set.
  useEffect(() => {
    if (!focusedCommentId || !displayTask || !contentRef.current) return;
    const target = contentRef.current.querySelector(
      `[data-comment-id="${CSS.escape(focusedCommentId)}"]`
    ) as HTMLElement | null;
    if (!target) return;
    target.scrollIntoView({ behavior: "smooth", block: "center" });
    target.classList.add("comment-highlight");
    const timer = window.setTimeout(() => target.classList.remove("comment-highlight"), 2500);
    return () => window.clearTimeout(timer);
  }, [focusedCommentId, displayTask?.id]);

  const formatEventValue = (value: unknown) => {
    if (value === null || value === undefined) {
      return "none";
    }
    if (typeof value === "string") {
      return value.length > 120 ? `${value.slice(0, 117)}...` : value;
    }
    const text = JSON.stringify(value);
    return text.length > 120 ? `${text.slice(0, 117)}...` : text;
  };

  const renderEventSummary = (event: IssueEvent) => {
    const payload = event.payload as Record<string, unknown>;
    switch (event.event_type) {
      case "issue_created":
        return `Issue created (${String(payload.issue_type)}, ${String(payload.status)})`;
      case "issue_deleted":
        return `Issue deleted (${String(payload.issue_type)})`;
      case "state_transition":
        return `State changed from ${String(payload.from_status)} to ${String(payload.to_status)}`;
      case "field_updated": {
        const changes = payload.changes as Record<
          string,
          { from: unknown; to: unknown }
        >;
        if (!changes) {
          return "Fields updated";
        }
        return (
          <div className="grid gap-1 text-xs text-muted">
            {Object.entries(changes).map(([field, change]) => (
              <div key={field}>
                <span className="font-semibold text-foreground">{field}</span>{" "}
                {formatEventValue(change.from)} → {formatEventValue(change.to)}
              </div>
            ))}
          </div>
        );
      }
      case "comment_added":
        return `Comment added by ${String(payload.comment_author)} (${String(payload.comment_id)})`;
      case "comment_updated":
        return `Comment updated by ${String(payload.comment_author)} (${String(payload.comment_id)})`;
      case "comment_deleted":
        return `Comment deleted by ${String(payload.comment_author)} (${String(payload.comment_id)})`;
      case "dependency_added":
        return `Dependency added: ${String(payload.dependency_type)} ${String(payload.target_id)}`;
      case "dependency_removed":
        return `Dependency removed: ${String(payload.dependency_type)} ${String(payload.target_id)}`;
      case "issue_localized":
        return `Issue moved from ${String(payload.from_location)} to ${String(payload.to_location)}`;
      case "issue_promoted":
        return `Issue moved from ${String(payload.from_location)} to ${String(payload.to_location)}`;
      default:
        return event.event_type;
    }
  };

  useEffect(() => {
    if (!task) {
      setDisplayTask(null);
      setOutgoingTask(null);
      setIncomingTask(null);
      setPagePhase("idle");
      return;
    }
    if (!displayTask) {
      setDisplayTask(task);
      return;
    }
    if (task.id === displayTask.id) {
      if (task !== displayTask) {
        setDisplayTask(task);
      }
      return;
    }
    const motion = document.documentElement.dataset.motion ?? "full";
    if (motion === "off") {
      setDisplayTask(task);
      return;
    }
    setPageDirection(navDirection === "pop" ? "pop" : "push");
    setOutgoingTask(displayTask);
    setIncomingTask(task);
    setPagePhase("ready");
  }, [task, displayTask, navDirection]);

  useEffect(() => {
    if (pagePhase !== "ready") {
      return;
    }
    let raf1 = 0;
    let raf2 = 0;
    raf1 = window.requestAnimationFrame(() => {
      raf2 = window.requestAnimationFrame(() => {
        setPagePhase("animating");
      });
    });
    return () => {
      window.cancelAnimationFrame(raf1);
      window.cancelAnimationFrame(raf2);
    };
  }, [pagePhase]);

  useEffect(() => {
    if (!isOpen) {
      setPanelOpenActive(false);
      return;
    }
    setPanelOpenActive(false);
    let raf1 = 0;
    let raf2 = 0;
    raf1 = window.requestAnimationFrame(() => {
      raf2 = window.requestAnimationFrame(() => {
        setPanelOpenActive(true);
      });
    });
    return () => {
      window.cancelAnimationFrame(raf1);
      window.cancelAnimationFrame(raf2);
    };
  }, [isOpen]);

  useEffect(() => {
    if (!displayTask || !contentRef.current) {
      return;
    }
    const motion = document.documentElement.dataset.motion ?? "full";
    if (motion === "off") {
      return;
    }
    const commentItems = contentRef.current.querySelectorAll(".detail-comment");
    if (commentItems.length === 0) {
      return;
    }
    gsap.fromTo(
      commentItems,
      { y: 12, opacity: 0 },
      {
        y: 0,
        opacity: 1,
        duration: motion === "reduced" ? 0.12 : 0.25,
        stagger: motion === "reduced" ? 0.02 : 0.05,
        ease: "power2.out"
      }
    );
  }, [displayTask?.id]);

  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const mermaidDivs = el.querySelectorAll(".mermaid:not([data-processed])");
    if (mermaidDivs.length === 0) return;
    const nodes = Array.from(mermaidDivs) as HTMLElement[];

    // Detect current theme and initialize Mermaid with it
    const isDark = document.documentElement.classList.contains("dark");
    mermaid.initialize({
      startOnLoad: false,
      theme: isDark ? "dark" : "default"
    });

    Promise.allSettled(
      nodes.map(async (node) => {
        const source = node.textContent ?? "";
        try {
          const { svg } = await mermaid.render(`mermaid-${Date.now()}-${Math.random().toString(36).slice(2)}`, source);
          node.innerHTML = svg;
          node.dataset.processed = "true";
        } catch (err: unknown) {
          const message = err instanceof Error ? err.message : String(err);
          node.innerHTML = `<pre style="color: var(--red-9, #e54d2e); white-space: pre-wrap; font-size: 12px; padding: 8px; border-radius: 6px; background: var(--card-muted, #1a1a1a);">Mermaid error:\n${message}</pre>`;
          node.dataset.processed = "true";
        }
      })
    );
  }, [displayTask]);

  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const d2Divs = el.querySelectorAll(".d2-diagram:not([data-processed])");
    if (d2Divs.length === 0) return;
    const nodes = Array.from(d2Divs) as HTMLElement[];

    // Detect current theme (light or dark)
    const isDark = document.documentElement.classList.contains("dark");
    const theme = isDark ? "dark" : "light";

    Promise.allSettled(
      nodes.map(async (node) => {
        const encoded = node.dataset.d2Source;
        if (!encoded) return;
        const source = decodeURIComponent(encoded);
        try {
          // Use our local D2 rendering endpoint with theme
          const response = await fetch("/api/render/d2", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source, theme })
          });
          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || `D2 render failed: ${response.statusText}`);
          }
          const data = await response.json();
          if (data.svg) {
            node.innerHTML = data.svg;
            node.dataset.processed = "true";
          } else {
            throw new Error("No SVG returned from D2 API");
          }
        } catch (err: unknown) {
          const message = err instanceof Error ? err.message : String(err);
          const isNotInstalled = message.includes("not installed");
          node.innerHTML = `<pre style="color: ${isNotInstalled ? 'var(--amber-9, #ffb224)' : 'var(--red-9, #e54d2e)'}; white-space: pre-wrap; font-size: 12px; padding: 8px; border-radius: 6px; background: var(--card-muted, #1a1a1a);">${isNotInstalled ? 'D2 diagram (d2 CLI not installed):\n' + source + '\n\nInstall d2: curl -fsSL https://d2lang.com/install.sh | sh -s --' : 'D2 rendering error:\n' + message}</pre>`;
          node.dataset.processed = "true";
        }
      })
    );
  }, [displayTask]);

  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const plantumlDivs = el.querySelectorAll(".plantuml-diagram:not([data-processed])");
    if (plantumlDivs.length === 0) return;
    const nodes = Array.from(plantumlDivs) as HTMLElement[];

    // Detect current theme (light or dark)
    const isDark = document.documentElement.classList.contains("dark");

    nodes.forEach((node) => {
      const encoded = node.dataset.plantumlSource;
      if (!encoded) return;
      const source = decodeURIComponent(encoded);

      // Add theme directive to PlantUML source
      let themedSource = source;
      if (isDark) {
        // For dark mode, add comprehensive skinparam styling
        if (!source.includes("skinparam")) {
          themedSource = source.replace(
            /@startuml/i,
            `@startuml
skinparam backgroundColor #1a1a1a
skinparam DefaultTextColor white
skinparam DefaultFontColor white
skinparam ArrowColor white
skinparam ArrowFontColor white
skinparam ArrowMessageAlign center
skinparam ActorBackgroundColor #2a2a2a
skinparam ActorBorderColor white
skinparam ActorFontColor white
skinparam ParticipantBackgroundColor #2a2a2a
skinparam ParticipantBorderColor white
skinparam ParticipantFontColor white
skinparam SequenceBoxBackgroundColor #2a2a2a
skinparam SequenceBoxBorderColor white
skinparam SequenceLifeLineBorderColor white
skinparam SequenceGroupBackgroundColor #2a2a2a
skinparam SequenceGroupBorderColor white
skinparam SequenceGroupBodyBackgroundColor #1a1a1a
skinparam SequenceGroupHeaderFontColor white
skinparam NoteBorderColor white
skinparam NoteBackgroundColor #2a2a2a
skinparam NoteFontColor white
skinparam SequenceDividerBackgroundColor #2a2a2a
skinparam SequenceDividerBorderColor white
skinparam SequenceDividerFontColor white`
          );
        }
      }

      // Encode the themed source
      const finalEncoded = plantumlEncoder.encode(themedSource);
      const img = document.createElement("img");
      img.src = `https://www.plantuml.com/plantuml/svg/${finalEncoded}`;
      img.alt = "PlantUML diagram";
      node.appendChild(img);
      node.dataset.processed = "true";
    });
  }, [displayTask]);

  const detailTask = layout === "auto" ? task : displayTask;

  const renderDetailContent = (taskToRender: TaskDetailIssue, withRef: boolean) => {
    const priorityName = priorityLookup[taskToRender.priority] ?? "medium";
    const comments = taskToRender.comments ?? [];
    const createdAt = taskToRender.created_at;
    const updatedAt = taskToRender.updated_at;
    const closedAt = taskToRender.closed_at;
    const showUpdated = Boolean(
      updatedAt && (!createdAt || updatedAt !== createdAt)
    );
    const DetailTypeIcon = getTypeIcon(taskToRender.type, taskToRender.status);
    const issueStyle =
      config ? buildIssueColorStyle(config, taskToRender) : undefined;
    const rawHtml = taskToRender.description
      ? (marked.parse(taskToRender.description, { async: false }) as string)
      : "";
    const descriptionHtml = rawHtml
      ? DOMPurify.sanitize(rawHtml, {
          USE_PROFILES: { html: true },
          ADD_ATTR: ["target", "rel"]
        })
      : "";
    const formattedCreated = createdAt
      ? formatTimestamp(createdAt, config?.time_zone)
      : null;
    const formattedUpdated = showUpdated && updatedAt
      ? formatTimestamp(updatedAt, config?.time_zone)
      : null;
    const formattedClosed = closedAt
      ? formatTimestamp(closedAt, config?.time_zone)
      : null;
    const subTasks = allIssues.filter(
      (issue) => issue.type === "sub-task" && issue.parent === taskToRender.id
    );
    const hasChildren = allIssues.some((i) => i.parent === taskToRender.id);
    const isFocused = focusedIssueId === taskToRender.id;

    // Collect ALL descendants recursively
    const allDescendantIds = new Set<string>();
    const queue = [taskToRender.id];
    while (queue.length > 0) {
      const current = queue.shift()!;
      const children = allIssues.filter(i => i.parent === current);
      children.forEach(child => {
        allDescendantIds.add(child.id);
        queue.push(child.id);
      });
    }

    // Filter out direct sub-tasks (already shown in Board) and the task itself
    const descendantIssues = allIssues
      .filter(issue =>
        allDescendantIds.has(issue.id) &&
        !(issue.type === "sub-task" && issue.parent === taskToRender.id)
      )
      .sort((a, b) => {
        // Sort by hierarchy depth, then by creation date
        const getDepth = (id: string): number => {
          let depth = 0;
          let current: TaskDetailIssue | undefined = allIssues.find(i => i.id === id);
          while (current?.parent) {
            depth++;
            current = allIssues.find(i => i.id === current!.parent);
          }
          return depth;
        };
        const depthDiff = getDepth(a.id) - getDepth(b.id);
        if (depthDiff !== 0) return depthDiff;
        return (a.created_at || "") < (b.created_at || "") ? -1 : 1;
      });

    // Calculate relative depth from the current task
    const getIssueDepth = (issueId: string): number => {
      let depth = 0;
      let current: TaskDetailIssue | undefined = allIssues.find(i => i.id === issueId);
      const visited = new Set<string>();

      while (current?.parent && !visited.has(current.id)) {
        visited.add(current.id);
        depth++;
        current = allIssues.find(i => i.id === current!.parent);
      }

      // Calculate depth of the root task
      let rootDepth = 0;
      let rootCurrent: TaskDetailIssue | undefined = taskToRender;
      const rootVisited = new Set<string>();

      while (rootCurrent?.parent && !rootVisited.has(rootCurrent.id)) {
        rootVisited.add(rootCurrent.id);
        rootDepth++;
        rootCurrent = allIssues.find(i => i.id === rootCurrent!.parent);
      }

      return depth - rootDepth - 1;
    };

    return (
      <div ref={withRef ? contentRef : null} className="flex flex-col h-full min-h-0">
        <div
          className="detail-accent-bar issue-card p-3 pb-0"
          style={issueStyle}
          data-status={taskToRender.status}
          data-type={taskToRender.type}
          data-priority={priorityName}
        >
          <div className="issue-accent-bar -m-3 mb-0 h-10 w-[calc(100%+1.5rem)] px-3 flex items-center pt-3 pb-3">
            <div className="issue-accent-row gap-2 w-full flex items-center justify-between min-w-0">
              <div className="issue-accent-left gap-1 inline-flex items-center min-w-0">
                <DetailTypeIcon className="issue-accent-icon" />
                <span className="issue-accent-id">{formatIssueId(taskToRender.id)}</span>
              </div>
              <div className="issue-accent-priority">{priorityName}</div>
            </div>
          </div>
        </div>
        <div className="detail-scroll flex-1 min-h-0 overflow-y-auto">
          <div
            className="detail-card issue-card p-3 grid gap-2"
            style={issueStyle}
            data-status={taskToRender.status}
            data-type={taskToRender.type}
            data-priority={priorityName}
          >
            <div className="grid gap-2">
              <div className="flex flex-wrap items-start justify-between gap-2 min-w-0">
                <div
                  ref={statusFlashRef}
                  className="text-xs font-semibold uppercase tracking-[0.3em] text-muted rounded px-2 py-1 -mx-2 -my-1 transition-colors min-w-0 max-[420px]:order-1"
                >
                  {taskToRender.type} · {taskToRender.status}
                </div>
                <div className="flex flex-wrap items-center gap-2 max-[420px]:order-2 max-[420px]:w-full max-[420px]:justify-start">
                  {hasChildren && (
                    <IconButton
                      icon={Focus}
                      label={isFocused ? "Remove focus" : "Focus on descendants"}
                      onClick={() => onFocus(taskToRender.id)}
                      aria-pressed={isFocused}
                      className={isFocused ? "bg-[var(--card-muted)]" : ""}
                    />
                  )}
                  <IconButton
                    icon={Maximize}
                    label={isMaximized ? "Exit full width" : "Fill width"}
                    onClick={onToggleMaximize}
                    aria-pressed={isMaximized}
                    className={isMaximized ? "bg-[var(--card-muted)]" : ""}
                  />
                  <IconButton icon={X} label="Close" onClick={onClose} />
                </div>
              </div>
              <h2
                ref={titleFlashRef}
                className="text-lg font-semibold text-selected rounded px-2 py-1 -mx-2 -my-1 transition-colors"
              >
                {taskToRender.title}
              </h2>
              {taskToRender.description ? (
                <div
                  ref={descriptionFlashRef}
                  className="issue-description-markdown text-sm text-selected mb-4 rounded px-2 py-1 -mx-2 -my-1 transition-colors"
                  dangerouslySetInnerHTML={{ __html: descriptionHtml }}
                />
              ) : null}
            </div>
            {formattedCreated ||
            formattedUpdated ||
            formattedClosed ||
            taskToRender.assignee ? (
              <div className="flex flex-wrap items-start gap-2 text-xs text-muted">
                <div className="flex flex-col gap-1">
                  {formattedCreated ? (
                    <div className="flex flex-wrap gap-2">
                      <span className="font-semibold uppercase tracking-[0.2em]">
                        Created
                      </span>
                      <span data-testid="issue-created-at">{formattedCreated}</span>
                    </div>
                  ) : null}
                  {formattedUpdated ? (
                    <div className="flex flex-wrap gap-2">
                      <span className="font-semibold uppercase tracking-[0.2em]">
                        Updated
                      </span>
                      <span data-testid="issue-updated-at">{formattedUpdated}</span>
                    </div>
                  ) : null}
                  {formattedClosed ? (
                    <div className="flex flex-wrap gap-2">
                      <span className="font-semibold uppercase tracking-[0.2em]">
                        Closed
                      </span>
                      <span data-testid="issue-closed-at">{formattedClosed}</span>
                    </div>
                  ) : null}
                </div>
                {taskToRender.assignee ? (
                  <div className="ml-auto text-right" data-testid="issue-assignee">
                    {taskToRender.assignee}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          <div className="detail-section p-3 grid gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <button
                className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] transition-colors ${
                  activeTab === "comments"
                    ? "bg-[var(--card-muted)] text-selected"
                    : "text-muted hover:text-foreground"
                }`}
                onClick={() => setActiveTab("comments")}
                type="button"
              >
                Comments
              </button>
              <button
                className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] transition-colors ${
                  activeTab === "events"
                    ? "bg-[var(--card-muted)] text-selected"
                    : "text-muted hover:text-foreground"
                }`}
                onClick={() => {
                  setActiveTab("events");
                  if (eventHistory.length === 0 && !eventLoading) {
                    void loadEvents(true);
                  }
                }}
                type="button"
              >
                Event History
              </button>
            </div>
            {activeTab === "comments" ? (
              <div className="grid gap-2">
                {comments.length === 0 ? (
                  <div className="text-sm text-muted">No comments yet.</div>
                ) : (
                  comments.map((comment, index) => {
                    const commentHtml = marked.parse(comment.text, { async: false }) as string;
                    return (
                      <div
                        key={`${comment.created_at}-${index}`}
                        className="detail-comment grid gap-2"
                        data-comment-id={comment.id}
                      >
                        <div className="text-xs font-semibold text-foreground">
                          {comment.author}
                        </div>
                        <div className="text-xs text-muted">
                          {formatTimestamp(comment.created_at, config?.time_zone)}
                        </div>
                        <div
                          className="issue-description-markdown text-sm text-foreground"
                          dangerouslySetInnerHTML={{
                            __html: DOMPurify.sanitize(commentHtml, {
                              USE_PROFILES: { html: true },
                              ADD_ATTR: ["target", "rel"]
                            })
                          }}
                        />
                      </div>
                    );
                  })
                )}
              </div>
            ) : (
              <div className="grid gap-3">
                {eventError ? (
                  <div className="text-sm text-muted">{eventError}</div>
                ) : null}
                {eventHistory.length === 0 && !eventLoading ? (
                  <div className="text-sm text-muted">No events yet.</div>
                ) : (
                  <div className="grid gap-3">
                    {eventHistory.map((event) => (
                      <div key={event.event_id} className="grid gap-1">
                        <div className="flex flex-wrap items-center gap-2 text-xs">
                          <span className="font-semibold text-foreground">
                            {event.actor_id}
                          </span>
                          <span className="text-muted">
                            {formatTimestamp(event.occurred_at, config?.time_zone)}
                          </span>
                        </div>
                        <div className="text-sm text-foreground">
                          {renderEventSummary(event)}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
                {eventLoading ? (
                  <div className="text-xs text-muted">Loading events...</div>
                ) : null}
                {eventCursor ? (
                  <button
                    className="w-fit rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.3em] text-muted hover:text-foreground transition-colors"
                    onClick={() => void loadEvents(false)}
                    type="button"
                  >
                    Load more
                  </button>
                ) : null}
              </div>
            )}
          </div>
          <div className="detail-section p-3 grid gap-2">
            <div className="text-xs font-semibold uppercase tracking-[0.3em] text-muted">
              Sub-tasks
            </div>
            {subTasks.length === 0 ? (
              <div className="text-sm text-muted">No sub-tasks yet for this item.</div>
            ) : (
              <Board
                columns={columns}
                issues={subTasks}
                priorityLookup={priorityLookup}
                config={config}
                transitionKey={`${taskToRender.id}-${subTasks.length}`}
                motion={{ mode: "css" }}
              />
            )}
          </div>
          <div className="detail-section p-3 grid gap-2">
            <div className="text-xs font-semibold uppercase tracking-[0.3em] text-muted">
              All Descendants
            </div>
            {descendantIssues.length === 0 ? (
              <div className="text-sm text-muted">No additional descendants.</div>
            ) : (
              <div className="grid gap-1">
                {descendantIssues.map((issue) => (
                  <DescendantLink
                    key={issue.id}
                    issue={issue}
                    depth={getIssueDepth(issue.id)}
                    priorityName={priorityLookup[issue.priority] ?? "medium"}
                    config={config}
                    onClick={() => {
                      if (onNavigateToDescendant) {
                        onNavigateToDescendant(issue);
                      }
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  return (
    <div
      ref={panelRef}
      className={`detail-column detail-layout-${layout} ${isVisible ? "detail-column-visible" : ""} ${
        panelOpenActive ? "detail-column-open" : "detail-column-closing"
      } flex flex-col`}
      data-width={widthPercent}
      onTransitionEnd={(event) => {
        if (!isOpen && event.target === event.currentTarget && event.propertyName === "transform") {
          onAfterClose();
        }
      }}
    >
      {detailTask ? (
        layout === "auto" ? (
          renderDetailContent(detailTask, true)
        ) : pagePhase !== "idle" && outgoingTask && incomingTask ? (
          <div className="detail-page-stack">
            <div
              className={`detail-page outgoing ${pagePhase === "animating" ? "animating" : ""}`}
              data-dir={pageDirection}
              key={`outgoing-${outgoingTask.id}`}
            >
              {renderDetailContent(outgoingTask, false)}
            </div>
            <div
              className={`detail-page incoming ${pagePhase === "animating" ? "animating" : ""}`}
              data-dir={pageDirection}
              key={`incoming-${incomingTask.id}`}
              onTransitionEnd={(event) => {
                if (event.target !== event.currentTarget) {
                  return;
                }
                if (event.propertyName !== "transform") {
                  return;
                }
                if (pagePhase === "animating" && incomingTask) {
                  setDisplayTask(incomingTask);
                  setOutgoingTask(null);
                  setIncomingTask(null);
                  setPagePhase("idle");
                }
              }}
            >
              {renderDetailContent(incomingTask, true)}
            </div>
          </div>
        ) : (
          renderDetailContent(detailTask, true)
        )
      ) : (
        <div className="detail-open flex-1 flex items-center justify-center text-muted text-sm p-6">
          Select an issue to view its details.
        </div>
      )}
    </div>
  );
}
