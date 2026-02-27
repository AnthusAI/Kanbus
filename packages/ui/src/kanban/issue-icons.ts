import {
  Bug,
  Bookmark,
  CheckSquare,
  Zap,
  Rocket,
  Square,
  Tag,
  Wrench,
  CornerDownRight
} from "lucide-react";

export function getTypeIcon(type: string, status?: string) {
  if (type === "task" || type === "story") {
    const taskIcon = status === "closed" ? CheckSquare : Square;
    return type === "task" ? taskIcon : Bookmark;
  }

  const iconMap: Record<string, any> = {
    initiative: Rocket,
    epic: Zap,
    "sub-task": CornerDownRight,
    bug: Bug,
    story: Bookmark,
    chore: Wrench
  };

  return iconMap[type] ?? Tag;
}
