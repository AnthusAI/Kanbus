import { useEffect, useState, type TransitionEvent } from "react";
import type { SidebarPhase, SidebarTarget } from "../types/console";

export type SidebarPanels = {
  filterOpen: boolean;
  settingsOpen: boolean;
  activeSidebar: SidebarTarget | null;
  exitingSidebar: SidebarTarget | null;
  sidebarReady: boolean;
  sidebarPhase: SidebarPhase;
  openSidebar: (target: SidebarTarget) => void;
  closeSidebar: (target: SidebarTarget) => void;
  toggleSettings: () => void;
  handleSidebarTransitionEnd: (event: TransitionEvent<HTMLDivElement>) => void;
};

export function useSidebarPanels(): SidebarPanels {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [activeSidebar, setActiveSidebar] = useState<SidebarTarget | null>(null);
  const [sidebarReady, setSidebarReady] = useState(false);
  const [sidebarPhase, setSidebarPhase] = useState<SidebarPhase>("closed");
  const [exitingSidebar, setExitingSidebar] = useState<SidebarTarget | null>(null);
  const sidebarOpen = filterOpen || settingsOpen;

  useEffect(() => {
    const id = window.requestAnimationFrame(() => setSidebarReady(true));
    return () => window.cancelAnimationFrame(id);
  }, []);

  useEffect(() => {
    if (filterOpen) {
      setActiveSidebar("filter");
    } else if (settingsOpen) {
      setActiveSidebar("settings");
    }
  }, [filterOpen, settingsOpen]);

  useEffect(() => {
    if (sidebarOpen) {
      setSidebarPhase((prev) => (prev === "open" || prev === "opening" ? prev : "opening"));
      return;
    }
    setSidebarPhase((prev) => (prev === "closed" ? prev : "closing"));
  }, [sidebarOpen]);

  useEffect(() => {
    if (sidebarPhase !== "opening") {
      return;
    }
    const id = window.requestAnimationFrame(() => setSidebarPhase("open"));
    return () => window.cancelAnimationFrame(id);
  }, [sidebarPhase]);

  const openSidebar = (target: SidebarTarget) => {
    const switching = sidebarOpen && activeSidebar && activeSidebar !== target;
    if (switching) {
      setExitingSidebar(activeSidebar);
      setSidebarPhase("opening");
    } else {
      setExitingSidebar(null);
    }
    if (target === "filter") {
      setSettingsOpen(false);
      setFilterOpen(true);
    } else {
      setFilterOpen(false);
      setSettingsOpen(true);
    }
    setActiveSidebar(target);
  };

  const closeSidebar = (target: SidebarTarget) => {
    if (target === "filter") {
      setFilterOpen(false);
    } else {
      setSettingsOpen(false);
    }
  };

  const toggleSettings = () => {
    setSettingsOpen((prev) => {
      const next = !prev;
      if (next) {
        setActiveSidebar("settings");
        setFilterOpen(false);
      }
      return next;
    });
  };

  const handleSidebarTransitionEnd = (event: TransitionEvent<HTMLDivElement>) => {
    if (event.propertyName !== "transform") {
      return;
    }
    if (event.target !== event.currentTarget) {
      return;
    }
    if (!sidebarOpen && sidebarPhase === "closing") {
      setSidebarPhase("closed");
      setActiveSidebar(null);
      setExitingSidebar(null);
      return;
    }
    const target = event.currentTarget as HTMLElement;
    const testId = target.dataset.testid;
    if (testId && exitingSidebar && testId.includes(exitingSidebar)) {
      setExitingSidebar(null);
    }
  };

  return {
    filterOpen,
    settingsOpen,
    activeSidebar,
    exitingSidebar,
    sidebarReady,
    sidebarPhase,
    openSidebar,
    closeSidebar,
    toggleSettings,
    handleSidebarTransitionEnd,
  };
}
