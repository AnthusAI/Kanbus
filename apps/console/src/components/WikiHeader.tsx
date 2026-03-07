import React, { useRef, useEffect, useState, useMemo } from "react";
import { ChevronLeft, ChevronRight, FileEdit, BookOpen, FileText, Edit2, Trash2, MoreHorizontal } from "lucide-react";
import { AnimatedSelector, type SelectorOption } from "@kanbus/ui";

interface WikiHeaderProps {
  currentRoute: string;
  canGoBack: boolean;
  canGoForward: boolean;
  onGoBack: () => void;
  onGoForward: () => void;
  onNavigate: (route: string) => void;
  viewMode: "read" | "edit";
  onChangeViewMode: (mode: "read" | "edit") => void;
  isFile: boolean;
  onCreatePage: () => void;
  onRename: () => void;
  onDelete: () => void;
}

export function WikiHeader({
  currentRoute,
  canGoBack,
  canGoForward,
  onGoBack,
  onGoForward,
  onNavigate,
  viewMode,
  onChangeViewMode,
  isFile,
  onCreatePage,
  onRename,
  onDelete
}: WikiHeaderProps) {
  const parts = currentRoute.split("/").filter(Boolean);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const readEditOptions = useMemo((): SelectorOption[] => [
    {
      id: "read",
      label: "Read",
      content: (
        <span className="selector-option">
          <BookOpen className="h-4 w-4" />
          <span className="selector-label">Read</span>
        </span>
      )
    },
    {
      id: "edit",
      label: "Edit",
      content: (
        <span className="selector-option">
          <FileEdit className="h-4 w-4" />
          <span className="selector-label">Edit</span>
        </span>
      )
    }
  ], []);

  useEffect(() => {
    if (!menuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [menuOpen]);

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 bg-[var(--card)] rounded-xl py-1.5 px-2">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onGoBack}
          disabled={!canGoBack}
          className="p-1 rounded-lg text-muted hover:bg-[var(--background)] hover:text-foreground disabled:opacity-30 disabled:hover:bg-transparent"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={onGoForward}
          disabled={!canGoForward}
          className="p-1 rounded-lg text-muted hover:bg-[var(--background)] hover:text-foreground disabled:opacity-30 disabled:hover:bg-transparent"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
        
        <div className="flex items-center text-sm ml-1">
          <button
            type="button"
            onClick={() => onNavigate("")}
            className="text-muted hover:text-foreground transition-colors font-medium"
          >
            Wiki
          </button>
          {parts.map((part, index) => {
            const route = parts.slice(0, index + 1).join("/");
            return (
              <React.Fragment key={route}>
                <span className="text-muted mx-2">/</span>
                <button
                  type="button"
                  onClick={() => onNavigate(route)}
                  className="text-muted hover:text-foreground transition-colors font-medium truncate max-w-[150px]"
                >
                  {part}
                </button>
              </React.Fragment>
            );
          })}
        </div>
      </div>

      <div className="flex items-center gap-1">
        {isFile && (
          <div className="mr-1">
            <AnimatedSelector
              name="wiki-view-mode"
              value={viewMode}
              onChange={(value) => onChangeViewMode(value as "read" | "edit")}
              options={readEditOptions}
              testIdPrefix="wiki-view-mode"
            />
          </div>
        )}

        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((prev) => !prev)}
            className="flex items-center justify-center p-1 rounded-lg bg-[var(--background)] text-muted hover:text-foreground transition-colors"
            title="Actions"
            aria-label="Actions"
            aria-haspopup="true"
            aria-expanded={menuOpen}
          >
            <MoreHorizontal className="w-4 h-4" />
          </button>
          {menuOpen && (
            <div
              className="absolute right-0 top-full mt-1 py-1 min-w-[160px] bg-[var(--card)] rounded-lg shadow-lg z-50"
              role="menu"
            >
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setMenuOpen(false);
                  onCreatePage();
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm text-muted hover:text-foreground hover:bg-[var(--background)] transition-colors"
              >
                <FileText className="w-4 h-4 shrink-0" />
                New page
              </button>
              {isFile && (
                <>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      onRename();
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm text-muted hover:text-foreground hover:bg-[var(--background)] transition-colors"
                  >
                    <Edit2 className="w-4 h-4 shrink-0" />
                    Rename page
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setMenuOpen(false);
                      onDelete();
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-left text-sm text-red-500/70 hover:text-red-500 hover:bg-red-500/10 transition-colors"
                  >
                    <Trash2 className="w-4 h-4 shrink-0" />
                    Delete page
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
