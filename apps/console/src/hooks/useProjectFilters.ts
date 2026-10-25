import { useEffect, useMemo, useRef, type Dispatch, type SetStateAction } from "react";
import type { ProjectConfig } from "../types/issues";

export type ProjectFilters = {
  projectLabels: string[];
  hasVirtualProjects: boolean;
  effectiveEnabledProjects: Set<string>;
  handleToggleProject: (label: string) => void;
};

export function useProjectFilters(
  config: ProjectConfig | undefined,
  enabledProjects: Set<string> | null,
  setEnabledProjects: Dispatch<SetStateAction<Set<string> | null>>
): ProjectFilters {
  const projectLabels = useMemo(() => {
    if (!config) {
      return [];
    }
    const labels = new Set<string>();
    if (config.project_key) {
      labels.add(config.project_key);
    }
    Object.keys(config.virtual_projects ?? {}).forEach((key) => labels.add(key));
    return Array.from(labels);
  }, [config]);
  const hasVirtualProjects = config
    ? Object.keys(config.virtual_projects ?? {}).length > 0
    : false;

  useEffect(() => {
    if (projectLabels.length > 0 && enabledProjects === null) {
      setEnabledProjects(new Set(projectLabels));
    }
  }, [projectLabels, enabledProjects]);

  const previousProjectLabelsRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (projectLabels.length === 0) {
      return;
    }
    const previous = previousProjectLabelsRef.current;
    const nextLabels = new Set(projectLabels);
    const newlyAdded = projectLabels.filter((label) => !previous.has(label));

    if (!enabledProjects || enabledProjects.size === 0) {
      setEnabledProjects(new Set(projectLabels));
    } else if (newlyAdded.length > 0) {
      setEnabledProjects((previousEnabled) => {
        const base = previousEnabled ? new Set(previousEnabled) : new Set<string>();
        newlyAdded.forEach((label) => base.add(label));
        return base;
      });
    }

    previousProjectLabelsRef.current = nextLabels;
  }, [projectLabels, enabledProjects]);

  const effectiveEnabledProjects = useMemo(() => {
    if (enabledProjects != null) {
      return enabledProjects;
    }
    return new Set(projectLabels);
  }, [enabledProjects, projectLabels]);

  const handleToggleProject = (label: string) => {
    setEnabledProjects((previous) => {
      const current = previous ?? new Set(projectLabels);
      const next = new Set(current);
      if (next.has(label)) {
        next.delete(label);
      } else {
        next.add(label);
      }
      return next;
    });
  };

  return { projectLabels, hasVirtualProjects, effectiveEnabledProjects, handleToggleProject };
}
