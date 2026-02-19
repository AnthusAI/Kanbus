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
import type { Issue, ProjectConfig } from "../types/issues";
import { Board } from "./Board";
import { buildIssueColorStyle, buildStatusBadgeStyle } from "../utils/issue-colors";
import { formatTimestamp } from "../utils/format-timestamp";
import { formatIssueId } from "../utils/format-issue-id";
import { IconButton } from "./IconButton";
import { getTypeIcon } from "../utils/issue-icons";
import { useFlashEffect } from "../hooks/useFlashEffect";
import { useTypingEffect } from "../hooks/useTypingEffect";

const markdownRenderer = new marked.Renderer();
markdownRenderer.link = (token: { href: string; title?: string | null; text: string }) => {
  const safeTitle = token.title ? ` title="${token.title}"` : "";
  return `<a href="${token.href}"${safeTitle} target="_blank" rel="noopener noreferrer">${token.text}</a>`;
};
markdownRenderer.code = (token: { text: string; lang?: string }) => {
  if (token.lang === "mermaid") {
    return `<div class="mermaid">${token.text}</div>`;
  }
  if (token.lang === "plantuml") {
    // Encode PlantUML source - theme will be added dynamically on render
    const encoded = encodeURIComponent(token.text);
    return `<div class="plantuml-diagram" data-plantuml-source="${encoded}"></div>`;
  }
  if (token.lang === "d2") {
    // Encode D2 source for client-side rendering via our API
    const encoded = encodeURIComponent(token.text);
    return `<div class="d2-diagram" data-d2-source="${encoded}"></div>`;
  }
  return `<pre><code class="language-${token.lang || ""}">${token.text}</code></pre>`;
};

marked.setOptions({
  gfm: true,
  breaks: true,
  renderer: markdownRenderer
});

// Mermaid will be re-initialized with the current theme when rendering

interface TaskDetailPanelProps {
  task: Issue | null;
  allIssues: Issue[];
  columns: string[];
  priorityLookup: Record<number, string>;
  config?: ProjectConfig;
  isOpen: boolean;
  isVisible: boolean;
  navDirection: "push" | "pop" | "none";
  widthPercent: number;
  onClose: () => void;
  onToggleMaximize: () => void;
  isMaximized: boolean;
  onAfterClose: () => void;
  onFocus: (issueId: string) => void;
  focusedIssueId: string | null;
  onNavigateToDescendant?: (issue: Issue) => void;
}

interface DescendantLinkProps {
  issue: Issue;
  depth: number;
  priorityName: string;
  config?: ProjectConfig;
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
      <div className="flex items-start gap-2 min-w-0">
        <div className="flex min-w-0 flex-1 items-start gap-2">
          <div className="shrink-0" style={{ width: `${depth * 12}px` }} aria-hidden="true" />
          {depth > 0 ? (
            <CornerDownRight className="shrink-0 w-3 h-3 text-muted" aria-hidden="true" />
          ) : null}
          <TypeIcon className="issue-accent-icon w-4 h-4 shrink-0" aria-hidden="true" />
          <div className="flex min-w-0 flex-1 items-baseline gap-2">
            <span className="issue-accent-id text-xs font-medium shrink-0">
              {formatIssueId(issue.id)}
            </span>
            <span className="text-sm text-foreground min-w-0 flex-1 break-words leading-snug">
              {issue.title}
            </span>
          </div>
        </div>
        <div className="ml-auto flex shrink-0 flex-wrap items-start justify-end gap-2">
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
  isOpen,
  isVisible,
  navDirection,
  widthPercent,
  onClose,
  onToggleMaximize,
  isMaximized,
  onAfterClose,
  onFocus,
  focusedIssueId,
  onNavigateToDescendant
}: TaskDetailPanelProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const [displayTask, setDisplayTask] = useState<Issue | null>(task);
  const [outgoingTask, setOutgoingTask] = useState<Issue | null>(null);
  const [incomingTask, setIncomingTask] = useState<Issue | null>(null);
  const [pagePhase, setPagePhase] = useState<"idle" | "ready" | "animating">("idle");
  const [pageDirection, setPageDirection] = useState<"push" | "pop">("push");
  const [panelOpenActive, setPanelOpenActive] = useState(false);

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
      theme: isDark ? "dark" : "default",
      suppressErrorRendering: true
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

  const detailTask = displayTask;

  const renderDetailContent = (taskToRender: Issue, withRef: boolean) => {
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
          let current: Issue | undefined = allIssues.find(i => i.id === id);
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
      let current: Issue | undefined = allIssues.find(i => i.id === issueId);
      const visited = new Set<string>();

      while (current?.parent && !visited.has(current.id)) {
        visited.add(current.id);
        depth++;
        current = allIssues.find(i => i.id === current!.parent);
      }

      // Calculate depth of the root task
      let rootDepth = 0;
      let rootCurrent: Issue | undefined = taskToRender;
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
            <div className="issue-accent-row gap-2 w-full flex items-center justify-between">
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
              <div className="flex items-center justify-between gap-2">
                <div
                  ref={statusFlashRef}
                  className="text-xs font-semibold uppercase tracking-[0.3em] text-muted rounded px-2 py-1 -mx-2 -my-1 transition-colors"
                >
                  {taskToRender.type} · {taskToRender.status}
                </div>
                <div className="flex items-center gap-2 translate-x-2">
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
          <div className="detail-section p-3 grid gap-2">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold uppercase tracking-[0.3em] text-muted">
                Comments
              </div>
            </div>
            <div className="grid gap-2">
              {comments.length === 0 ? (
                <div className="text-sm text-muted">No comments yet.</div>
              ) : (
                comments.map((comment, index) => {
                  const commentHtml = marked.parse(comment.text, { async: false }) as string;
                  return (
                    <div key={`${comment.created_at}-${index}`} className="detail-comment grid gap-2">
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
      className={`detail-column ${isVisible ? "detail-column-visible" : ""} ${
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
        pagePhase !== "idle" && outgoingTask && incomingTask ? (
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
      ) : null}
    </div>
  );
}
