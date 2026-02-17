import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";
import {
  X,
  Bug,
  BookOpen,
  CheckSquare,
  ListChecks,
  Rocket,
  Square,
  Tag,
  Wrench,
  CornerDownRight,
  Maximize
} from "lucide-react";
import gsap from "gsap";
import type { Issue, ProjectConfig } from "../types/issues";
import { Board } from "./Board";
import { buildIssueColorStyle } from "../utils/issue-colors";
import { formatTimestamp } from "../utils/format-timestamp";
import { formatIssueId } from "../utils/format-issue-id";
import { IconButton } from "./IconButton";

const markdownRenderer = new marked.Renderer();
markdownRenderer.link = (href, title, text) => {
  const safeTitle = title ? ` title="${title}"` : "";
  return `<a href="${href}"${safeTitle} target="_blank" rel="noopener noreferrer">${text}</a>`;
};

marked.setOptions({
  gfm: true,
  breaks: true,
  mangle: false,
  headerIds: false,
  renderer: markdownRenderer
});

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
}

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
  onAfterClose
}: TaskDetailPanelProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const [displayTask, setDisplayTask] = useState<Issue | null>(task);
  const [outgoingTask, setOutgoingTask] = useState<Issue | null>(null);
  const [incomingTask, setIncomingTask] = useState<Issue | null>(null);
  const [pagePhase, setPagePhase] = useState<"idle" | "ready" | "animating">("idle");
  const [pageDirection, setPageDirection] = useState<"push" | "pop">("push");
  const [panelOpenActive, setPanelOpenActive] = useState(false);

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

  useLayoutEffect(() => {
    if (pagePhase !== "ready") {
      return;
    }
    const frame = window.requestAnimationFrame(() => {
      setPagePhase("animating");
    });
    return () => window.cancelAnimationFrame(frame);
  }, [pagePhase]);

  useEffect(() => {
    if (!isOpen) {
      setPanelOpenActive(false);
      return;
    }
    setPanelOpenActive(false);
    const frame = window.requestAnimationFrame(() => {
      setPanelOpenActive(true);
    });
    return () => window.cancelAnimationFrame(frame);
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
    const taskIcon = taskToRender.status === "closed" ? CheckSquare : Square;
    const DetailTypeIcon =
      {
        initiative: Rocket,
        epic: ListChecks,
        task: taskIcon,
        "sub-task": CornerDownRight,
        bug: Bug,
        story: BookOpen,
        chore: Wrench
      }[taskToRender.type] ?? Tag;
    const issueStyle =
      config ? buildIssueColorStyle(config, taskToRender) : undefined;
    const rawHtml = taskToRender.description
      ? marked.parse(taskToRender.description)
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
                <div className="text-xs font-semibold uppercase tracking-[0.3em] text-muted">
                  {taskToRender.type} · {taskToRender.status}
                </div>
                <div className="flex items-center gap-2 translate-x-2">
                  <IconButton
                    icon={Maximize}
                    label={isMaximized ? "Exit full width" : "Fill width"}
                    onClick={onToggleMaximize}
                    aria-pressed={isMaximized}
                    className={isMaximized ? "bg-[var(--card-muted)]" : ""}
                  />
                  <IconButton
                    icon={X}
                    label="Close"
                    onClick={onClose}
                  />
                </div>
              </div>
                <h2 className="text-lg font-semibold text-selected">
                  {taskToRender.title}
                </h2>
                {taskToRender.description ? (
                  <div
                    className="issue-description-markdown text-sm text-selected mb-4"
                    dangerouslySetInnerHTML={{ __html: descriptionHtml }}
                  />
                ) : null}
              </div>
              {(formattedCreated || formattedUpdated || formattedClosed || taskToRender.assignee) ? (
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
                  comments.map((comment, index) => (
                    <div key={`${comment.created_at}-${index}`} className="detail-comment grid gap-2">
                      <div className="text-xs font-semibold text-foreground">
                        {comment.author}
                      </div>
                      <div className="text-xs text-muted">
                        {formatTimestamp(comment.created_at, config?.time_zone)}
                      </div>
                      <div className="text-sm text-foreground">{comment.text}</div>
                    </div>
                  ))
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
            >
              {renderDetailContent(outgoingTask, false)}
            </div>
            <div
              className={`detail-page incoming ${pagePhase === "animating" ? "animating" : ""}`}
              data-dir={pageDirection}
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
