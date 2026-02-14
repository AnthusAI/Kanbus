import React, { useEffect, useRef, useState } from "react";
import {
  X,
  Bug,
  BookOpen,
  CheckSquare,
  ListChecks,
  Rocket,
  Tag,
  Wrench,
  CornerDownRight
} from "lucide-react";
import gsap from "gsap";
import type { Issue } from "../types/issues";
import { Board } from "./Board";

interface TaskDetailPanelProps {
  task: Issue | null;
  subTasks: Issue[];
  columns: string[];
  priorityLookup: Record<number, string>;
  isOpen: boolean;
  widthPercent: number;
  onClose: () => void;
}

export function TaskDetailPanel({
  task,
  subTasks,
  columns,
  priorityLookup,
  isOpen,
  widthPercent,
  onClose
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

  const detailTask = displayTask;
  const priorityName = detailTask
    ? priorityLookup[detailTask.priority] ?? "medium"
    : "";
  const comments = detailTask?.comments ?? [];
  const DetailTypeIcon =
    {
      initiative: Rocket,
      epic: ListChecks,
      task: CheckSquare,
      "sub-task": CornerDownRight,
      bug: Bug,
      story: BookOpen,
      chore: Wrench
    }[detailTask?.type ?? ""] ?? Tag;

  return (
    <div
      ref={panelRef}
      className={`detail-column ${isOpen ? "detail-column-open" : ""} flex flex-col`}
      data-width={widthPercent}
    >
      {detailTask ? (
        <div ref={contentRef} className="flex flex-col h-full min-h-0">
          <div
            className="detail-accent-bar issue-card p-3"
            data-status={detailTask.status}
            data-type={detailTask.type}
            data-priority={priorityName}
          >
            <div className="issue-accent-bar -m-3 mb-0 h-10 w-[calc(100%+1.5rem)] px-3 flex items-center pt-3 pb-3">
              <div className="issue-accent-row gap-2 w-full flex items-center justify-between">
                <div className="issue-accent-left gap-1 inline-flex items-center min-w-0">
                  <DetailTypeIcon className="issue-accent-icon" />
                  <span className="issue-accent-id">{detailTask.id}</span>
                </div>
                <div className="issue-accent-priority">{priorityName}</div>
              </div>
            </div>
          </div>
          <div className="detail-scroll flex-1 min-h-0 overflow-y-auto">
            <div
              className="detail-card issue-card p-3 grid gap-2"
              data-status={detailTask.status}
              data-type={detailTask.type}
              data-priority={priorityName}
            >
            <div className="grid gap-2">
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs font-semibold uppercase tracking-[0.3em] text-muted">
                  {detailTask.type} · {detailTask.status}
                </div>
                <button
                  className="rounded-full bg-background px-1 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-muted h-7"
                  onClick={onClose}
                  type="button"
                >
                  <span className="flex items-center gap-1.5">
                    <X className="h-4 w-4" />
                    <span>Close</span>
                  </span>
                </button>
              </div>
                <h2 className="text-lg font-semibold text-foreground">
                  {detailTask.title}
                </h2>
                {detailTask.description ? (
                  <p className="text-sm text-foreground">{detailTask.description}</p>
                ) : null}
                {detailTask.assignee ? (
                  <div className="text-xs text-muted">Assignee: {detailTask.assignee}</div>
                ) : null}
              </div>
            </div>
            <div className="detail-section p-2 grid gap-2">
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
                    <div key={`${comment.created_at}-${index}`} className="detail-comment p-2 grid gap-2">
                      <div className="text-xs font-semibold text-foreground">
                        {comment.author}
                      </div>
                      <div className="text-xs text-muted">{comment.created_at}</div>
                      <div className="text-sm text-foreground">{comment.text}</div>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="detail-section p-2 grid gap-2">
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
