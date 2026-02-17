import React, { useEffect, useRef, useState } from "react";
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

interface TaskDetailPanelProps {
  task: Issue | null;
  subTasks: Issue[];
  columns: string[];
  priorityLookup: Record<number, string>;
  config?: ProjectConfig;
  isOpen: boolean;
  widthPercent: number;
  onClose: () => void;
  onToggleMaximize: () => void;
  isMaximized: boolean;
}

export function TaskDetailPanel({
  task,
  subTasks,
  columns,
  priorityLookup,
  config,
  isOpen,
  widthPercent,
  onClose,
  onToggleMaximize,
  isMaximized
}: TaskDetailPanelProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  const [displayTask, setDisplayTask] = useState<Issue | null>(task);
  const previousTaskRef = useRef<Issue | null>(null);

  useEffect(() => {
    if (task?.id !== previousTaskRef.current?.id) {
      previousTaskRef.current = task ?? null;
    }
  }, [task]);

  useEffect(() => {
    if (!task) {
      return;
    }
    if (!contentRef.current) {
      setDisplayTask(task);
      return;
    }
    const motion = document.documentElement.dataset.motion ?? "full";
    if (motion === "off") {
      setDisplayTask(task);
      return;
    }

    const duration = motion === "reduced" ? 0.12 : 0.25;
    const timeline = gsap.timeline({
      onComplete: () => {
        setDisplayTask(task);
        if (contentRef.current) {
          gsap.fromTo(
            contentRef.current,
            { x: -40, opacity: 0 },
            { x: 0, opacity: 1, duration, ease: "power2.out" }
          );
          const commentItems = contentRef.current.querySelectorAll(".detail-comment");
          if (commentItems.length > 0) {
            gsap.fromTo(
              commentItems,
              { y: 12, opacity: 0 },
              {
                y: 0,
                opacity: 1,
                duration: motion === "reduced" ? 0.12 : 0.25,
                stagger: motion === "reduced" ? 0.02 : 0.05,
                ease: "power2.out",
                delay: motion === "reduced" ? 0.05 : 0.1
              }
            );
          }
        }
      }
    });

    timeline.to(contentRef.current, {
      x: 40,
      opacity: 0,
      duration,
      ease: "power2.in"
    });
  }, [task?.id]);

  // Update displayTask when task data changes (not just ID).
  // This handles real-time updates via SSE for the same task.
  useEffect(() => {
    if (!task || !displayTask) {
      return;
    }
    // Same task ID but different data = update without animation
    if (task.id === displayTask.id && task !== displayTask) {
      setDisplayTask(task);
    }
  }, [task]);

  const detailTask = displayTask;
  const priorityName = detailTask
    ? priorityLookup[detailTask.priority] ?? "medium"
    : "";
  const comments = detailTask?.comments ?? [];
  const createdAt = detailTask?.created_at;
  const updatedAt = detailTask?.updated_at;
  const closedAt = detailTask?.closed_at;
  const showUpdated = Boolean(
    updatedAt && (!createdAt || updatedAt !== createdAt)
  );
  const taskIcon =
    detailTask?.status === "closed" ? CheckSquare : Square;
  const DetailTypeIcon =
    {
      initiative: Rocket,
      epic: ListChecks,
      task: taskIcon,
      "sub-task": CornerDownRight,
      bug: Bug,
      story: BookOpen,
      chore: Wrench
    }[detailTask?.type ?? ""] ?? Tag;
  const issueStyle =
    detailTask && config ? buildIssueColorStyle(config, detailTask) : undefined;
  const formattedCreated = createdAt
    ? formatTimestamp(createdAt, config?.time_zone)
    : null;
  const formattedUpdated = showUpdated && updatedAt
    ? formatTimestamp(updatedAt, config?.time_zone)
    : null;
  const formattedClosed = closedAt
    ? formatTimestamp(closedAt, config?.time_zone)
    : null;

  return (
    <div
      ref={panelRef}
      className={`detail-column ${isOpen ? "detail-column-open" : ""} flex flex-col`}
      data-width={widthPercent}
    >
      {detailTask ? (
        <div ref={contentRef} className="flex flex-col h-full min-h-0">
          <div
            className="detail-accent-bar issue-card p-3 pb-0"
            style={issueStyle}
            data-status={detailTask.status}
            data-type={detailTask.type}
            data-priority={priorityName}
          >
            <div className="issue-accent-bar -m-3 mb-0 h-10 w-[calc(100%+1.5rem)] px-3 flex items-center pt-3 pb-3">
              <div className="issue-accent-row gap-2 w-full flex items-center justify-between">
                <div className="issue-accent-left gap-1 inline-flex items-center min-w-0">
                  <DetailTypeIcon className="issue-accent-icon" />
                  <span className="issue-accent-id">{formatIssueId(detailTask.id)}</span>
                </div>
                <div className="issue-accent-priority">{priorityName}</div>
              </div>
            </div>
          </div>
          <div className="detail-scroll flex-1 min-h-0 overflow-y-auto">
            <div
              className="detail-card issue-card p-3 grid gap-2"
              style={issueStyle}
              data-status={detailTask.status}
              data-type={detailTask.type}
              data-priority={priorityName}
            >
              <div className="grid gap-2">
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs font-semibold uppercase tracking-[0.3em] text-muted">
                  {detailTask.type} · {detailTask.status}
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
                  {detailTask.title}
                </h2>
                {detailTask.description ? (
                  <p className="text-sm text-selected">{detailTask.description}</p>
                ) : null}
              </div>
              {(formattedCreated || formattedUpdated || formattedClosed || detailTask.assignee) ? (
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
                  {detailTask.assignee ? (
                    <div className="ml-auto text-right" data-testid="issue-assignee">
                      {detailTask.assignee}
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
                  transitionKey={`${detailTask.id}-${subTasks.length}`}
                />
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
