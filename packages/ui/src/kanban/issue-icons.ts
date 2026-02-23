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
