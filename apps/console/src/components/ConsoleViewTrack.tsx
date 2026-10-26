import { Suspense, lazy, type Dispatch, type RefObject, type SetStateAction } from "react";
import { Board } from "@kanbus/ui";
import type { NavAction, PanelMode } from "../types/console";
import type { Issue, ProjectConfig } from "../types/issues";
import { addIssueComment, setIssueAssignment, transitionIssue } from "../api/client";
import { DetailResizer } from "./DetailResizer";

const TaskDetailPanel = lazy(() =>
  import("@kanbus/ui/task-detail-panel").then((module) => ({ default: module.TaskDetailPanel }))
);
const MetricsPanel = lazy(() =>
  import("./MetricsPanel").then((module) => ({ default: module.MetricsPanel }))
);
const CurrentStatusPanel = lazy(() =>
  import("./CurrentStatusPanel").then((module) => ({ default: module.CurrentStatusPanel }))
);
const WikiPanel = lazy(() =>
  import("./WikiPanel").then((module) => ({ default: module.WikiPanel }))
);
const BOARD_MOTION = { mode: "css" } as const;

type ConsoleViewTrackProps = {
  animate: boolean;
  viewTrackTransform: string;
  panelMode: PanelMode;
  visitedPanelModes: ReadonlySet<PanelMode>;
  apiBase: string;
  config: ProjectConfig | undefined;
  issues: Issue[];
  filteredIssues: Issue[];
  metricsIssues: Issue[];
  columns: string[];
  priorityLookup: Record<number, string>;
  transitionKey: string;
  hasLocalIssues: boolean;
  projectLabels: string[];
  collapsedColumns: Set<string>;
  onToggleCollapse: (columnName: string) => void;
  selectedTask: Issue | null;
  isDetailOpen: boolean;
  isDetailVisible: boolean;
  detailMaximized: boolean;
  detailWidth: number;
  detailNavDirection: NavAction;
  layoutFrameRef: RefObject<HTMLDivElement>;
  setDetailWidth: Dispatch<SetStateAction<number>>;
  setDetailMaximized: Dispatch<SetStateAction<boolean>>;
  setIsResizing: Dispatch<SetStateAction<boolean>>;
  setDetailClosing: Dispatch<SetStateAction<boolean>>;
  onSelectIssue: (issue: Issue) => void;
  onTaskClose: () => void;
  onFocus: (issueId: string) => void;
  focusedIssueId: string | null;
  focusedCommentId: string | null;
  replaceIssueInSnapshot: (issueId: string, issue: Issue) => void;
  wikiRoutePath: string | null;
  onWikiDirtyChange: (dirty: boolean) => void;
  onWikiRouteChange: (path: string) => void;
};

export function ConsoleViewTrack({
  animate,
  viewTrackTransform,
  panelMode,
  visitedPanelModes,
  apiBase,
  config,
  issues,
  filteredIssues,
  metricsIssues,
  columns,
  priorityLookup,
  transitionKey,
  hasLocalIssues,
  projectLabels,
  collapsedColumns,
  onToggleCollapse,
  selectedTask,
  isDetailOpen,
  isDetailVisible,
  detailMaximized,
  detailWidth,
  detailNavDirection,
  layoutFrameRef,
  setDetailWidth,
  setDetailMaximized,
  setIsResizing,
  setDetailClosing,
  onSelectIssue,
  onTaskClose,
  onFocus,
  focusedIssueId,
  focusedCommentId,
  replaceIssueInSnapshot,
  wikiRoutePath,
  onWikiDirtyChange,
  onWikiRouteChange,
}: ConsoleViewTrackProps) {
  return (
    <div
      className={`view-track${animate ? " view-track-animate" : ""}`}
      style={{ transform: viewTrackTransform }}
    >
        <div
          className={`view-panel ${
            panelMode === "now" ? "view-panel-active" : "view-panel-inactive"
          }`}
          data-testid="current-status-view"
          aria-hidden={panelMode !== "now"}
        >
          <div
            className="layout-slot layout-slot-metrics p-0 min-[321px]:p-1 sm:p-2 md:p-3"
          >
            {visitedPanelModes.has("now") ? (
            <Suspense fallback={null}>
            <CurrentStatusPanel
              issues={issues}
              config={config}
              priorityLookup={priorityLookup}
              boardTitle={config?.name ?? ""}
              defaultTreeExpanded={config?.right_now?.default_tree_expanded ?? false}
              onSelectIssue={onSelectIssue}
              selectedIssueId={selectedTask?.id ?? null}
              apiBase={apiBase}
            />
            </Suspense>
            ) : null}
          </div>
        </div>
        <div
          className={`view-panel ${
            panelMode === "board" ? "view-panel-active" : "view-panel-inactive"
          }${isDetailVisible ? " view-panel-detail-visible" : ""}`}
          data-testid="board-view"
          aria-hidden={panelMode !== "board"}
        >
      <div
        className={`layout-slot layout-slot-board h-full p-0 min-[321px]:p-1 sm:p-2 md:p-3 overflow-hidden${
          detailMaximized ? " hidden" : ""
        }`}
      >
        {!detailMaximized ? (
          <Board
            columns={columns}
            issues={filteredIssues}
            priorityLookup={priorityLookup}
            config={config}
            onSelectIssue={onSelectIssue}
            selectedIssueId={selectedTask?.id ?? null}
            transitionKey={transitionKey}
            detailOpen={isDetailOpen}
            collapsedColumns={collapsedColumns}
            motion={BOARD_MOTION}
            onToggleCollapse={onToggleCollapse}
          />
        ) : null}
      </div>
          {isDetailVisible ? (
            <DetailResizer
              layoutFrameRef={layoutFrameRef}
              detailWidth={detailWidth}
              detailMaximized={detailMaximized}
              setDetailWidth={setDetailWidth}
              setDetailMaximized={setDetailMaximized}
              setIsResizing={setIsResizing}
            />
          ) : null}
          <Suspense fallback={null}>
          <TaskDetailPanel
            task={selectedTask}
            allIssues={issues}
            isOpen={isDetailOpen}
            isVisible={isDetailVisible}
            navDirection={detailNavDirection}
            widthPercent={detailMaximized ? 100 : detailWidth}
            columns={columns}
            priorityLookup={priorityLookup}
            config={config}
            apiBase={apiBase}
            onClose={onTaskClose}
            onToggleMaximize={() => setDetailMaximized((prev) => !prev)}
            isMaximized={detailMaximized}
            onAfterClose={() => setDetailClosing(false)}
            onFocus={onFocus}
            focusedIssueId={focusedIssueId}
            focusedCommentId={focusedCommentId}
            onNavigateToDescendant={onSelectIssue}
            onAddComment={async (issueId, text) => {
              const result = await addIssueComment(apiBase, issueId, text);
              replaceIssueInSnapshot(issueId, result.issue);
            }}
            onChangeAssignment={async (issueId, choice) => {
              const result = await setIssueAssignment(apiBase, issueId, choice);
              replaceIssueInSnapshot(issueId, result.issue);
            }}
            onChangeStatus={async (issueId, status) => {
              const result = await transitionIssue(apiBase, issueId, status);
              replaceIssueInSnapshot(issueId, result.issue);
            }}
          />
          </Suspense>
        </div>
        <div
          className={`view-panel ${
            panelMode === "wiki" ? "view-panel-active" : "view-panel-inactive"
          }`}
          data-testid="wiki-view"
          aria-hidden={panelMode !== "wiki"}
        >
          <div className="layout-slot layout-slot-metrics p-0 min-[321px]:p-1 sm:p-2 md:p-3">
            {apiBase && visitedPanelModes.has("wiki") ? (
              <Suspense fallback={null}>
              <WikiPanel
                apiBase={apiBase}
                isActive={panelMode === "wiki"}
                onDirtyChange={onWikiDirtyChange}
                initialRoutePath={wikiRoutePath ?? ""}
                onRouteChange={onWikiRouteChange}
              />
              </Suspense>
            ) : null}
          </div>
        </div>
        <div
          className={`view-panel ${
            panelMode === "metrics" ? "view-panel-active" : "view-panel-inactive"
          }`}
          data-testid="metrics-view"
          aria-hidden={panelMode !== "metrics"}
        >
          <div
            className="layout-slot layout-slot-metrics p-0 min-[321px]:p-1 sm:p-2 md:p-3"
          >
            {config && visitedPanelModes.has("metrics") ? (
              <Suspense fallback={null}>
              <MetricsPanel
                issues={metricsIssues}
                config={config}
                hasLocalIssues={hasLocalIssues}
                projectLabels={projectLabels}
              />
              </Suspense>
            ) : null}
          </div>
        </div>
      </div>
  );
}
