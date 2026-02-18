import {
  Bug,
  BookOpen,
  CheckSquare,
  ListChecks,
  Rocket,
  Square,
  Tag,
  Wrench,
  CornerDownRight
} from "lucide-react";

/**
 * Get the appropriate icon component for an issue type and status.
 * @param type - The issue type (task, bug, story, etc.)
 * @param status - Optional issue status (used for task/story to show checked/unchecked)
 * @returns The Lucide icon component for the issue type
 */
export function getTypeIcon(type: string, status?: string) {
  if (type === "task" || type === "story") {
    const taskIcon = status === "closed" ? CheckSquare : Square;
    return type === "task" ? taskIcon : BookOpen;
  }

  const iconMap: Record<string, any> = {
    initiative: Rocket,
    epic: ListChecks,
    "sub-task": CornerDownRight,
    bug: Bug,
    story: BookOpen,
    chore: Wrench
  };

  return iconMap[type] ?? Tag;
}
