import React, { useEffect, useMemo, useState } from "react";
import {
  createWikiPage,
  deleteWikiPage,
  fetchWikiPage,
  fetchWikiPages,
  renameWikiPage,
  renderWikiPage,
  updateWikiPage
} from "../api/client";
import { WikiPageTree } from "./WikiPageTree";
import { WikiEditor } from "./WikiEditor";
import { WikiPreview } from "./WikiPreview";

interface WikiPanelProps {
  apiBase: string;
  isActive: boolean;
  onDirtyChange: (dirty: boolean) => void;
}

export function WikiPanel({ apiBase, isActive, onDirtyChange }: WikiPanelProps) {
  const [pages, setPages] = useState<string[]>([]);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [savedContent, setSavedContent] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [renderedMarkdown, setRenderedMarkdown] = useState("");
  const [renderError, setRenderError] = useState<string | null>(null);
  const [isLoadingPages, setIsLoadingPages] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isRendering, setIsRendering] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRenderTimer, setAutoRenderTimer] = useState<number | null>(null);

  const isDirty = useMemo(() => draftContent !== savedContent, [draftContent, savedContent]);

  useEffect(() => {
    onDirtyChange(isDirty);
  }, [isDirty, onDirtyChange]);

  useEffect(() => {
    if (!isActive) {
      return;
    }
    void refreshPages();
  }, [isActive]);

  useEffect(() => {
    if (!wikiShouldAutoRender()) {
      return;
    }
    if (autoRenderTimer) {
      window.clearTimeout(autoRenderTimer);
    }
    const timer = window.setTimeout(() => {
      void handleRender();
    }, 800);
    setAutoRenderTimer(timer);
    return () => {
      window.clearTimeout(timer);
    };
  }, [draftContent, selectedPath, isActive]);

  useEffect(() => {
    if (!wikiShouldAutoRender() || isDirty) {
      return;
    }
    void handleRender();
  }, [selectedPath, isActive]);

  useEffect(() => {
    if (!isActive || !isDirty) {
      return;
    }
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isActive, isDirty]);

  async function refreshPages() {
    setIsLoadingPages(true);
    setError(null);
    try {
      const result = await fetchWikiPages(apiBase);
      setPages(result.pages);
      if (result.pages.length > 0) {
        const initial = result.pages[0];
        if (!selectedPath || !result.pages.includes(selectedPath)) {
          await selectPath(initial, false);
        }
      } else {
        setSelectedPath(null);
        setSavedContent("");
        setDraftContent("");
        setRenderedMarkdown("");
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsLoadingPages(false);
    }
  }

  function wikiShouldAutoRender() {
    return isActive && Boolean(selectedPath);
  }

  async function selectPath(path: string, allowPrompt = true) {
    if (isDirty && allowPrompt) {
      const proceed = window.confirm("You have unsaved changes. Leave without saving?");
      if (!proceed) {
        return;
      }
    }
    setError(null);
    try {
      const page = await fetchWikiPage(apiBase, path);
      setSelectedPath(page.path);
      setSavedContent(page.content);
      setDraftContent(page.content);
      setRenderedMarkdown("");
      setRenderError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleCreate() {
    const path = window.prompt("Enter new page path (relative, ends with .md):", "index.md");
    if (!path) {
      return;
    }
    setError(null);
    try {
      await createWikiPage(apiBase, { path, content: "# New page\n" });
      await refreshPages();
      await selectPath(path, false);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleRename(path: string) {
    const next = window.prompt("Rename page to:", path);
    if (!next || next === path) {
      return;
    }
    if (isDirty) {
      const proceed = window.confirm("Unsaved changes will be lost. Continue?");
      if (!proceed) {
        return;
      }
    }
    setError(null);
    try {
      await renameWikiPage(apiBase, { from_path: path, to_path: next, overwrite: false });
      await refreshPages();
      await selectPath(next, false);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleDelete(path: string) {
    const proceed = window.confirm(`Delete page "${path}"?`);
    if (!proceed) {
      return;
    }
    setError(null);
    try {
      await deleteWikiPage(apiBase, path);
      const nextPages = pages.filter((entry) => entry !== path);
      setPages(nextPages);
      if (selectedPath === path) {
        setSelectedPath(nextPages[0] ?? null);
        if (nextPages[0]) {
          await selectPath(nextPages[0], false);
        } else {
          setSavedContent("");
          setDraftContent("");
          setRenderedMarkdown("");
        }
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function handleSave() {
    if (!selectedPath) {
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      await updateWikiPage(apiBase, { path: selectedPath, content: draftContent });
      setSavedContent(draftContent);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsSaving(false);
    }
  }

  function handleReset() {
    setDraftContent(savedContent);
    setRenderError(null);
  }

  async function handleRender() {
    if (!selectedPath) {
      return;
    }
    setIsRendering(true);
    setRenderError(null);
    try {
      const payload =
        draftContent !== savedContent
          ? { path: selectedPath, content: draftContent }
          : { path: selectedPath };
      const rendered = await renderWikiPage(apiBase, payload);
      setRenderedMarkdown(rendered.rendered_markdown);
    } catch (err) {
      setRenderError((err as Error).message);
    } finally {
      setIsRendering(false);
    }
  }

  return (
    <div className="wiki-panel">
      <WikiPageTree
        pages={pages}
        selectedPath={selectedPath}
        onSelectPath={(path) => void selectPath(path, true)}
        onCreate={handleCreate}
        onRename={handleRename}
        onDelete={handleDelete}
      />
      <WikiEditor
        path={selectedPath}
        draftContent={draftContent}
        isDirty={isDirty}
        isSaving={isSaving}
        onChange={setDraftContent}
        onSave={handleSave}
        onReset={handleReset}
      />
      <WikiPreview
        path={selectedPath}
        renderedMarkdown={renderedMarkdown}
        renderError={renderError}
        isRendering={isRendering}
        onRender={handleRender}
      />
      {isLoadingPages ? (
        <div className="loading-overlay">
          <div className="loading-overlay-card">Loading wiki...</div>
        </div>
      ) : null}
      {error ? <div className="wiki-error">{error}</div> : null}
    </div>
  );
}
